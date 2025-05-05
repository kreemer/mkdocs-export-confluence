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
        host: https://<YOUR_CONFLUENCE_DOMAIN>/wiki/
        space: <YOUR_SPACE>
        parent_page: <YOUR_ROOT_PARENT_PAGE>
        username: <YOUR_USERNAME_TO_CONFLUENCE>
        password: <YOUR_PASSWORD_TO_CONFLUENCE>
        enabled: true
        dry_run: false
```


## Parameters:

| Config | Description |
| --- | --- |
| host | | THe host of the confluence page, should end with `/wiki/` |
| space | | The space key where the files should be saved |
| parent_page | | (Optional) if all pages should be nested under a common parent page |
| username | | The username of the user |
| password | | The password or api key of the user |
| enabled | True | If this plugin should be processed |
| dry_run | False | If the documents should actually be uploaded |


### Requirements
- mimetypes
- mistune
