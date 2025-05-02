from setuptools import setup, find_packages

setup(
    name="mkdocs-export-confluence",
    version="0.0.1",
    description="MkDocs plugin for uploading markdown documentation to Confluence via Confluence REST API",
    keywords="mkdocs markdown confluence documentation rest python",
    url="https://github.com/kreemer/mkdocs-export-confluence/",
    author="kreemer",
    author_email="kevin@familie-studer.ch",
    license="MIT",
    python_requires=">=3.11",
    install_requires=["mkdocs>=1.1", "jinja2", "mistune>=3.0", "requests"],
    packages=find_packages(),
    entry_points={
        "mkdocs.plugins": [
            "mkdocs-export-confluence = mkdocs_export_confluence.plugin:MkdocsExportConfluence"
        ]
    },
)
