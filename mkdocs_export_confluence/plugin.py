import re
from urllib.parse import urlparse
import mkdocs.config
import mkdocs.config.base
from mkdocs.exceptions import PluginError
from mkdocs.plugins import BasePlugin
from dataclasses import dataclass
from mkdocs.config import config_options
import mkdocs
import logging
import mistune
import mimetypes

import mkdocs.structure
import mkdocs.structure.nav
import mkdocs.structure.pages
import requests
import os
import hashlib

import uuid
import re
from pathlib import Path
from typing import List, NamedTuple, Optional, Any
from urllib.parse import unquote, urlparse

import mistune


class MkdocsExportConfluenceConfig(mkdocs.config.base.Config):
    host = config_options.Type(str)
    space = config_options.Type(str)
    username = config_options.Type(str)
    password = config_options.Type(str)
    enabled = config_options.Type(bool, default=True)
    dry_run = config_options.Type(bool, default=False)
    parent_page = config_options.Optional(config_options.Type(str))


class MkdocsExportConfluence(BasePlugin[MkdocsExportConfluenceConfig]):

    def __init__(self):
        self.session = requests.Session()
        self.session_file = requests.Session()
        self.logger = logging.getLogger("mkdocs.plugins.{__name__}")
        self.items = []
        self.enabled = True
        self.confluence_renderer = ConfluenceRenderer(enable_relative_links=True)
        self.confluence_mistune = mistune.Markdown(
            renderer=self.confluence_renderer, plugins=[admonition]
        )
        self.relative_links = []
        self.attachements: list[tuple[Item, any]] = []

    def on_config(self, config):
        self.logger.debug("on_config called")

        if not self.enabled:
            self.logger.info("Plugin is disabled")
            return

        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        self.session.auth = (
            self.config["username"],
            self.config["password"],
        )

        self.session_file.headers.update({"X-Atlassian-Token": "nocheck"})
        self.session_file.auth = (
            self.config["username"],
            self.config["password"],
        )

    def on_nav(self, nav: mkdocs.structure.nav.Navigation, config, files):
        self.logger.debug("on_nav called")
        if not self.enabled:
            return

        self.items = self.__process_navigation(nav)

    def on_page_markdown(self, markdown, /, *, page, config, files):
        self.logger.debug("on_page_markdown called")
        if not self.enabled:
            self.logger.debug("Plugin is disabled, skipping on_page_markdown")
            return

        for item in self.items:
            if item.structure == page:
                self.logger.debug(f"Found page in tree: {page}")

                item.markdown = markdown
                item.confluence_body = self.confluence_mistune(markdown)

                for attachment in self.confluence_renderer.attachments:
                    self.attachements.append((item, attachment))
                    self.logger.debug(f"Found attachment: {attachment}")
                    item.confluence_body = re.sub(
                        r'ri:filename="' + attachment + '"',
                        r'ri:filename="'
                        + hashlib.md5(attachment.encode("utf-8")).hexdigest()
                        + '"',
                        item.confluence_body,
                    )

                for link in self.confluence_renderer.relative_links:
                    self.logger.debug(f"Found relative link: {link}")
                    self.relative_links.append((item, link))

                self.confluence_renderer.reinit()

        return markdown

    def __process_navigation(self, nav: mkdocs.structure.nav.Navigation):
        self.logger.debug(f"Building internal navigation tree")
        tree = self.__process_navigation_item(nav.items, None)

        return tree

    def __process_navigation_item(self, items, parent):
        tree = []

        for item in items:
            if item.is_page:
                self.logger.debug(f"Appending page {item} to tree")
                tree.append(Item(structure=item, parent=parent))

        for item in items:
            if item.is_section:
                parent_item = Item(structure=item, parent=parent)
                tree.append(parent_item)
                self.logger.debug(f"Searching section {item} for pages")
                sub_tree = self.__process_navigation_item(item.children, parent_item)
                for sub_item in sub_tree:
                    tree.append(sub_item)

        return tree

    def on_post_build(self, config, **kwargs):
        self.logger.debug("on_post_build called")
        if not self.enabled:
            self.logger.debug("Plugin is disabled, skipping on_post_build")
            return

        space_id = self.__get_confluence_space_id(self.config["space"])
        self.config["space_id"] = space_id

        self.logger.info(f"Confluence space ID: {space_id}")

        self.config["parent_page_id"] = None
        if self.config["parent_page"] is not None:
            self.logger.info(f"Confluence parent page: {self.config['parent_page']}")
            parent_page = self.__find_confluence_page_id_by_title(
                self.config["parent_page"]
            )
            if parent_page is None:
                raise PluginError(
                    f"Parent page \"{self.config['parent_page']}\" not found in Confluence"
                )

            parent_page_id = parent_page["id"]
            self.config["parent_page_id"] = parent_page_id

        self.__process_confluence_names()
        self.__process_confluence_page_id()
        self.__process_relative_links()
        self.__process_items()
        self.__process_attachements()
        return True

    def __process_attachements(self):
        self.logger.debug("Processing attachments")
        for item, attachment in self.attachements:
            self.logger.info(f"Uploading attachment {attachment}")
            directory = os.path.dirname(item.structure.file.abs_src_path)
            attachement_path = os.path.normpath(os.path.join(directory, attachment))
            attachement_name = hashlib.md5(attachment.encode("utf-8")).hexdigest()

            if not os.path.exists(attachement_path):
                self.logger.debug(f"Attachment file does not exist: {attachement_path}")
                continue

            url = (
                self.config["host"]
                + "rest/api/content/"
                + item.confluence_id
                + "/child/attachment"
            )

            content_type, encoding = mimetypes.guess_type(attachement_path)
            if content_type is None:
                content_type = "multipart/form-data"

            if self.config["dry_run"]:
                self.logger.info(
                    f"Dry run: not uploading attachment {attachement_name} to {url}"
                )
                continue

            self.logger.debug(f"Uploading attachment {attachement_name} to {url}")

            response = self.session_file.request(
                "PUT",
                url,
                files={
                    "file": (
                        attachement_name,
                        open(attachement_path, "rb"),
                        content_type,
                    ),
                    "comment": "Attachment for " + item.confluence_name,
                },
            )

            if response.status_code != 200:
                raise PluginError(
                    f"Failed to upload attachment: {response} {response.text}"
                )

    def __process_relative_links(self):
        self.logger.debug("Processing relative links")
        self.logger.debug(f"Found {len(self.relative_links)} relative links")
        for link in self.relative_links:
            page: mkdocs.structure.pages.Page = link[0].structure
            parsed_link = os.path.normpath(
                os.path.join(os.path.dirname(page.file.src_path), link[1].path)
            )

            self.logger.debug(f"Parsed link: {page.title} -> {parsed_link}")

            found = False
            for item in self.items:
                if (
                    not found
                    and item.structure.is_page
                    and item.structure.file.src_path == parsed_link
                ):
                    found = True
                    link[0].confluence_body = re.sub(
                        r'<a href="' + link[1].replacement + '">(.*?)</a>',
                        r'<ac:link><ri:page ri:content-title="'
                        + item.confluence_name
                        + '" /><ac:link-body>\\1</ac:link-body></ac:link>',
                        link[0].confluence_body,
                    )

    def __get_confluence_space_id(self, name):
        url = self.config["host"] + "api/v2/spaces?keys=" + name + ""
        self.logger.debug(f"Sending request to url: {url}")
        response = self.session.get(url)

        return response.json()["results"][0]["id"]

    def __process_confluence_names(self):
        unique_titles = []
        for item in self.items:
            item.confluence_name = item.structure.title
            if item.confluence_name in unique_titles:
                self.logger.debug(f"Duplicate title found: {item.confluence_name}")
                while item.confluence_name in unique_titles:
                    item.confluence_name = f"{item.confluence_name}1"
            unique_titles.append(item.confluence_name)

    def __process_confluence_page_id(self):
        for item in self.items:
            result = self.__find_confluence_page_id(item)
            if result is not None:
                self.logger.debug(
                    f"Found page ID for {item.confluence_name}: {result['id']}"
                )
                item.confluence_id = result["id"]
                item.confluence_version = result["version"]["number"]

    def __find_confluence_page_id(self, item):
        page_name = item.confluence_name.replace(" ", "+")
        self.logger.debug(f"Finding page ID for {page_name}")

        return self.__find_confluence_page_id_by_title(page_name)

    def __find_confluence_page_id_by_title(self, title):
        url = (
            self.config["host"]
            + "api/v2/pages?title="
            + title
            + "&space-id="
            + self.config["space_id"]
            + ""
        )
        self.logger.debug(f"Sending request to url: {url}")
        response = self.session.get(url)
        json = response.json()

        if json["results"]:
            return json["results"][0]
        else:
            return None

    def __process_items(self):
        for item in self.items:
            if item.confluence_id is None:
                self.logger.info(f'Creating new page "{item.confluence_name}"')
                self.__create_confluence_page(item)
            else:
                self.logger.info(f'Updating page "{item.confluence_name}"')
                self.__update_confluence_page(item)

    def __create_confluence_page(self, item):
        url = self.config["host"] + "api/v2/pages"

        parent_id = item.parent.confluence_id if item.parent else None
        if parent_id is None:
            parent_id = self.config["parent_page_id"]

        data = {
            "spaceId": self.config["space_id"],
            "status": "current",
            "title": item.confluence_name,
            "parentId": parent_id,
            "body": {
                "storage": {"value": item.confluence_body, "representation": "storage"}
            },
        }

        if self.config["dry_run"]:
            self.logger.info(
                f"Dry run: not creating page {item.confluence_name} to {url}"
            )
            return

        response = self.session.post(url, json=data)
        if response.status_code == 200:
            item.confluence_id = response.json()["id"]
        else:
            raise PluginError(f"Failed to create item: {response.text}")

    def __update_confluence_page(self, item):
        url = self.config["host"] + "api/v2/pages/" + item.confluence_id

        parent_id = item.parent.confluence_id if item.parent else None
        if parent_id is None:
            parent_id = self.config["parent_page_id"]

        data = {
            "id": item.confluence_id,
            "status": "current",
            "parentId": parent_id,
            "title": item.confluence_name,
            "body": {
                "storage": {"value": item.confluence_body, "representation": "storage"}
            },
            "version": {"number": item.confluence_version + 1},
        }

        if self.config["dry_run"]:
            self.logger.info(
                f"Dry run: not updating page {item.confluence_name} to {url}"
            )
            return

        response = self.session.put(url, json=data)
        if response.status_code != 200:
            raise PluginError(f"Failed to create item: {response.text}")


@dataclass
class Item:
    structure: mkdocs.structure.pages.StructureItem
    parent: mkdocs.structure.pages.StructureItem = None
    markdown: str = None
    confluence_id: str = None
    confluence_name: str = None
    confluence_version: int = None
    confluence_body: str = ""


class RelativeLink(NamedTuple):
    path: str
    fragment: str
    replacement: str
    original: str
    escaped_original: str


class ConfluenceTag(object):
    def __init__(self, name, text="", attrib=None, namespace="ac", cdata=False):
        self.name = name
        self.text = text
        self.namespace = namespace
        if attrib is None:
            attrib = {}
        self.attrib = attrib
        self.children = []
        self.cdata = cdata

    def render(self):
        namespaced_name = self.add_namespace(self.name, namespace=self.namespace)
        namespaced_attribs = {
            self.add_namespace(
                attribute_name, namespace=self.namespace
            ): attribute_value
            for attribute_name, attribute_value in self.attrib.items()
        }

        content = "<{}{}>{}{}</{}>".format(
            namespaced_name,
            (
                " {}".format(
                    " ".join(
                        [
                            '{}="{}"'.format(name, value)
                            for name, value in sorted(namespaced_attribs.items())
                        ]
                    )
                )
                if namespaced_attribs
                else ""
            ),
            "".join([child.render() for child in self.children]),
            "<![CDATA[{}]]>".format(self.text) if self.cdata else self.text,
            namespaced_name,
        )
        return "{}\n".format(content)

    @staticmethod
    def add_namespace(tag, namespace):
        return "{}:{}".format(namespace, tag)

    def append(self, child):
        self.children.append(child)


class ConfluenceRenderer(mistune.HTMLRenderer):
    def __init__(
        self,
        strip_header=False,
        remove_text_newlines=False,
        enable_relative_links=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.strip_header = strip_header
        self.remove_text_newlines = remove_text_newlines
        self.attachments = list()
        self.title = None
        self.enable_relative_links = enable_relative_links
        self.relative_links: List[RelativeLink] = list()

    def reinit(self):
        self.attachments = list()
        self.relative_links = list()
        self.title = None

    def header(self, text, level, raw=None):
        if self.title is None and level == 1:
            self.title = text
            # Don't duplicate page title as a header
            if self.strip_header:
                return ""

        return super(ConfluenceRenderer, self).header(text, level, raw=raw)

    def structured_macro(self, name, text=""):
        return ConfluenceTag("structured-macro", attrib={"name": name}, text=text)

    def parameter(self, name, value):
        parameter_tag = ConfluenceTag("parameter", attrib={"name": name})
        parameter_tag.text = value
        return parameter_tag

    def plain_text_body(self, text):
        body_tag = ConfluenceTag("plain-text-body", cdata=True)
        body_tag.text = text
        return body_tag

    def rich_text_body(self, text):
        body_tag = ConfluenceTag("rich-text-body", cdata=False)
        body_tag.text = text
        return body_tag

    def link(self, text, url, title=None):
        parsed_link = urlparse(url)
        if (
            self.enable_relative_links
            and (not parsed_link.scheme and not parsed_link.netloc)
            and parsed_link.path
        ):
            # relative link
            replacement_link = f"md2cf-internal-link-{uuid.uuid4()}"
            self.relative_links.append(
                RelativeLink(
                    # make sure to unquote the url as relative paths
                    # might have escape sequences
                    path=unquote(parsed_link.path),
                    replacement=replacement_link,
                    fragment=parsed_link.fragment,
                    original=url,
                    escaped_original=mistune.escape_url(url),
                )
            )
            url = replacement_link
        return super(ConfluenceRenderer, self).link(text, url, title)

    def text(self, text):
        if self.remove_text_newlines:
            text = text.replace("\n", " ")

        return super().text(text)

    def block_code(self, code, info=None):
        root_element = self.structured_macro("code")
        if info is not None:
            lang_parameter = self.parameter(name="language", value=info)
            root_element.append(lang_parameter)
        root_element.append(self.parameter(name="linenumbers", value="true"))
        root_element.append(self.plain_text_body(code))
        return root_element.render()

    def image(self, alt, url, title=None, width=None, height=None):
        attributes = {
            "alt": alt,
            "title": title if title is not None else alt,
        }
        if width:
            attributes["width"] = width
        if height:
            attributes["height"] = height

        root_element = ConfluenceTag(name="image", attrib=attributes)
        parsed_source = urlparse(url)
        if not parsed_source.netloc:
            url_tag = ConfluenceTag(
                "attachment", attrib={"filename": url}, namespace="ri"
            )
            self.attachments.append(url)
        else:
            url_tag = ConfluenceTag("url", attrib={"value": url}, namespace="ri")
        root_element.append(url_tag)

        return root_element.render()

    def strikethrough(self, text):
        return f"""<span style="text-decoration: line-through;">{text}</span>"""

    def task_list_item(self, text, checked=False, **attrs):
        return f"""
               <ac:task-list>
               <ac:task>
                   <ac:task-status>{"in" if not checked else ""}complete</ac:task-status>
                   <ac:task-body>{text}</ac:task-body>
               </ac:task>
               </ac:task-list>
               """

    def block_spoiler(self, text):
        lines = text.splitlines(keepends=True)
        firstline = re.sub("<.*?>", "", lines[0])

        root_element = self.structured_macro("expand")
        title_param = self.parameter(name="title", value=firstline)
        root_element.append(title_param)

        root_element.append(self.rich_text_body("".join(lines[1:])))
        return root_element.render()

    def mark(self, text):
        return f"""<span style="background: yellow;">{text}</span>"""

    def insert(self, text):
        return f"""<span style="color: red;">{text}</span>"""

    def admonition(self, text: str, name: str, **attrs) -> str:
        confluence_mapping = {
            "tip": "tip",
            "attention": "warning",
            "caution": "warning",
            "danger": "warning",
            "error": "warning",
            "hint": "tip",
            "important": "note",
            "note": "info",
            "warning": "warning",
        }

        adm_class = confluence_mapping.get(name, "info")
        root_element = self.structured_macro(name=adm_class, text=text)

        if attrs["content"]:
            content = self.rich_text_body(attrs["content"])
            root_element.append(content)

        return root_element.render()

    def admonition_title(self, text: str) -> str:
        param = self.parameter(name="title", value=text)
        return param.render()

    def admonition_content(self, text: str) -> str:
        body = self.rich_text_body(text)
        return body.render()

    def block_image(
        self,
        src: str,
        alt: Optional[str] = None,
        width: Optional[str] = None,
        height: Optional[str] = None,
        **attrs: Any,
    ) -> str:
        return self.image(alt, src, alt, width, height)


def admonition(md: mistune.Markdown):
    md.block.register(
        "admonition",
        r"^^!!!\s+(?P<name>\w+)\s*\n(?P<text>(?:\s{4}.*\n?)+)",
        parse_admonition,
        before="code",
    )


def parse_admonition(
    block: mistune.BlockParser, m: re.Match[str], state: mistune.BlockState
) -> str:
    name = m.group("name")
    text = m.group("text")

    text = re.sub(r"^\s{4}", "", text, flags=re.MULTILINE)

    text = mistune.escape(text)

    state.append_token(
        {"type": "admonition", "attrs": {"name": name, "text": "", "content": text}}
    )
    return m.end() + 1
