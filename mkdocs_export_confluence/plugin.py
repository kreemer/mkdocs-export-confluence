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
from md2cf.confluence_renderer import ConfluenceRenderer, ConfluenceTag
import mistune
import mimetypes

import mkdocs.structure
import mkdocs.structure.nav
import mkdocs.structure.pages
import requests
import os
import hashlib


class MkdocsExportConfluenceConfig(mkdocs.config.base.Config):
    confluence_host = config_options.Optional(config_options.Type(str))
    confluence_space = config_options.Optional(config_options.Type(str))
    confluence_parent_page = config_options.Optional(config_options.Type(str))
    confluence_username = config_options.Optional(config_options.Type(str))
    confluence_password = config_options.Optional(config_options.Type(str))
    enabled = config_options.Type(bool, default=True)


class MkdocsExportConfluence(BasePlugin[MkdocsExportConfluenceConfig]):

    def __init__(self):
        self.session = requests.Session()
        self.session_file = requests.Session()
        self.logger = logging.getLogger("mkdocs.plugins.{__name__}")
        self.items = []
        self.config = {}
        self.enabled = True
        self.confluence_renderer = MyConfluenceRenderer(
            use_xhtml=True, enable_relative_links=True
        )
        self.confluence_mistune = mistune.Markdown(renderer=self.confluence_renderer)
        self.relative_links = []
        self.attachements: list[tuple[Item, any]] = []

    def on_config(self, config: mkdocs.config.Config):
        self.logger.debug("on_config called")
        self.enabled = config.get("enabled") != False and os.getenv("ENABLED") != "0"

        if not self.enabled:
            self.logger.info("Plugin is disabled")
            return

        self.__process_config(config)

        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        self.session.auth = (
            self.config["confluence_username"],
            self.config["confluence_password"],
        )

        self.session_file.headers.update({"X-Atlassian-Token": "nocheck"})
        self.session_file.auth = (
            self.config["confluence_username"],
            self.config["confluence_password"],
        )

    def __process_config(self, config: mkdocs.config.Config):
        if (
            config.get("confluence_host") is None
            and os.getenv("CONFLUENCE_HOST") is None
        ):
            self.logger.info("Confluence host is required, disable plugin")
            self.enabled = False
            return
        else:
            self.config["confluence_host"] = config.get("confluence_host") or os.getenv(
                "CONFLUENCE_HOST"
            )

        if (
            config.get("confluence_space") is None
            and os.getenv("CONFLUENCE_SPACE") is None
        ):
            self.logger.info("Confluence space is required, disable plugin")
            self.enabled = False
            return
        else:
            self.config["confluence_space"] = config.get(
                "confluence_space"
            ) or os.getenv("CONFLUENCE_SPACE")

        if (
            config.get("confluence_username") is None
            and os.getenv("CONFLUENCE_USERNAME") is None
        ):
            self.logger.info("Confluence username is required, disable plugin")
            self.enabled = False
            return
        else:
            self.config["confluence_username"] = config.get(
                "confluence_username"
            ) or os.getenv("CONFLUENCE_USERNAME")

        if (
            config.get("confluence_password") is None
            and os.getenv("CONFLUENCE_PASSWORD") is None
        ):
            self.logger.info("Confluence password is required, disable plugin")
            self.enabled = False
            return
        else:
            self.config["confluence_password"] = config.get(
                "confluence_password"
            ) or os.getenv("CONFLUENCE_PASSWORD")

        self.config["confluence_parent_page"] = config.get("confluence_parent_page")

    def on_nav(self, nav: mkdocs.structure.nav.Navigation, config, files):
        self.logger.debug("on_nav called")
        if not self.enabled:
            self.logger.debug("Plugin is disabled, skipping on_nav")
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

        space_id = self.__get_confluence_space_id(self.config["confluence_space"])
        self.config["confluence_space_id"] = space_id

        self.logger.info(f"Confluence space ID: {space_id}")
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
                self.config["confluence_host"]
                + "rest/api/content/"
                + item.confluence_id
                + "/child/attachment"
            )

            content_type, encoding = mimetypes.guess_type(attachement_path)
            if content_type is None:
                content_type = "multipart/form-data"

            self.logger.debug(f"Uploading attachment {attachement_name} to {url}")
            self.logger.debug(f"Attachment content type: {content_type}")
            self.logger.debug(f"Attachment path: {attachement_path}")
            self.logger.debug(f"Attachment name: {attachement_name}")

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
                    self.logger.debug(f"Checking page: {item.structure.title}")
                    self.logger.debug(f"Page URL: {item.structure.file.src_path}")

                    self.logger.debug(f"Found page for link: {item.confluence_name}")

                    link[0].confluence_body = re.sub(
                        r'<a href="' + link[1].replacement + '">(.*)</a>',
                        r'<ac:link><ri:page ri:content-title="'
                        + item.confluence_name
                        + '" /><ac:link-body>\\1</ac:link-body></ac:link>',
                        link[0].confluence_body,
                    )

    def __get_confluence_space_id(self, name):
        url = self.config["confluence_host"] + "api/v2/spaces?keys=" + name + ""
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

        url = (
            self.config["confluence_host"]
            + "api/v2/pages?title="
            + page_name
            + "&space-id="
            + self.config["confluence_space_id"]
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
        url = self.config["confluence_host"] + "api/v2/pages"

        data = {
            "spaceId": self.config["confluence_space_id"],
            "status": "current",
            "title": item.confluence_name,
            "parentId": item.parent.confluence_id if item.parent else None,
            "body": {
                "storage": {"value": item.confluence_body, "representation": "storage"}
            },
        }

        response = self.session.post(url, json=data)
        if response.status_code == 200:
            item.confluence_id = response.json()["id"]
        else:
            raise PluginError(f"Failed to create item: {response.text}")

    def __update_confluence_page(self, item):
        url = self.config["confluence_host"] + "api/v2/pages/" + item.confluence_id

        self.logger.debug(
            f"Updating page {item.confluence_name} with ID {item.confluence_id}"
        )
        self.logger.debug(f"Body: {item.confluence_body}")

        data = {
            "id": item.confluence_id,
            "status": "current",
            "parentId": item.parent.confluence_id if item.parent else None,
            "title": item.confluence_name,
            "body": {
                "storage": {"value": item.confluence_body, "representation": "storage"}
            },
            "version": {"number": item.confluence_version + 1},
        }

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


class MyConfluenceRenderer(ConfluenceRenderer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attachments = list()
        self.relative_links = list()
        self.title = None

    def image(self, src, title, text):
        attributes = {"alt": text}
        if title:
            attributes["title"] = title

        root_element = ConfluenceTag(name="image", attrib=attributes)
        parsed_source = urlparse(src)
        if not parsed_source.netloc:
            url_tag = ConfluenceTag(
                "attachment", attrib={"filename": src}, namespace="ri"
            )
            self.attachments.append(src)
        else:
            url_tag = ConfluenceTag("url", attrib={"value": src}, namespace="ri")
        root_element.append(url_tag)

        return root_element.render()
