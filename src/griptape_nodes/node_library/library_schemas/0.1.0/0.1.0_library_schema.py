from __future__ import annotations

from pydantic import BaseModel


class LibrarySchema(BaseModel):
    class LibraryMetadata(BaseModel):
        author: str
        description: str
        library_version: str
        engine_version: str
        tags: list[str]

    class Category(BaseModel):
        id: str
        color: str
        title: str
        description: str
        icon: str

    class Node(BaseModel):
        class_name: str
        file_path: str
        metadata: LibrarySchema.NodeMetadata

    class NodeMetadata(BaseModel):
        category: str
        description: str
        display_name: str

    name: str
    library_schema_version: str
    metadata: LibrarySchema.LibraryMetadata
    categories: list[LibrarySchema.Category]
    nodes: list[LibrarySchema.Node]
