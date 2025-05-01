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
    python_requires=">=3.6",
    install_requires=["mkdocs>=1.1", "jinja2", "mistune", "md2cf", "requests"],
    packages=find_packages("src"),
    entry_points={"mkdocs.plugins": ["mkdocs-export-confluence = src.plugin:MkdocsExportConfluence"]},
)
