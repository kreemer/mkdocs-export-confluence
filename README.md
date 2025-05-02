![PyPI](https://img.shields.io/pypi/v/mkdocs-export-confluence)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mkdocs-export-confluence)
![GitHub contributors](https://img.shields.io/github/contributors/kreemer/mkdocs-export-confluence)
![PyPI - License](https://img.shields.io/pypi/l/mkdocs-export-confluence)
![PyPI - Python Version](https://img.shields.io/pypi/kreemer/mkdocs-export-confluence)
# mkdocs-export-confluence

MkDocs plugin that converts markdown pages into confluence markup
and export it to the Confluence page

## Setup
Install the plugin using pip:

`pip install mkdocs-export-confluence`

Activate the plugin in `mkdocs.yml`:

```yaml
plugins:
  - search
  - mkdocs-export-confluence
```

More information about plugins in the [MkDocs documentation: mkdocs-plugins](https://www.mkdocs.org/user-guide/plugins/).

## Usage

Use following config and adjust it according to your needs:

```yaml
  - mkdocs-export-confluence:
        host: https://<YOUR_CONFLUENCE_DOMAIN>/wiki
        space: <YOUR_SPACE>
        parent_page: <YOUR_ROOT_PARENT_PAGE>
        username: <YOUR_USERNAME_TO_CONFLUENCE>
        password: <YOUR_PASSWORD_TO_CONFLUENCE>
        enabled: true
```


## Parameters:

You can also enter the variables as environment variables:

| Config | Env |
| --- | --- |
| host | CONFLUENCE_HOST |
| space | CONFLUENCE_SPACE |
| parent_page | CONFLUENCE_PARENT_PAGE |
| username | CONFLUENCE_USERNAME |
| password | CONFLUENCE_PASSWORD |
| enabled | ENABLED |

You can enter instead of the password an api key.

### Requirements
- mimetypes
- mistune
