from pydantic import BaseModel, Field


class SearchPost(BaseModel):
    id: str
    url: str
    title: str
    author: str = ""
    likes: str = ""
    cover_url: str = ""


class SearchResults(BaseModel):
    query: str
    posts: list[SearchPost]
    has_more: bool
    warning: str | None = None


class Post(BaseModel):
    id: str
    url: str
    title: str
    content: str
    author: str = ""
    date: str = ""
    likes: str = ""
    images: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    warning: str | None = None
