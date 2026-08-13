from sqlalchemy.orm import Session

from app.exceptions.roadmap import RoadmapItemNotFoundError
from app.models.roadmap import RoadmapItem
from app.repositories.roadmap_repository import RoadmapRepository


class RoadmapItemUpdateService:
    """Ownership-checked edits to a single roadmap item. The only writer
    of `is_user_edited` from a live request -- always forced true here,
    never accepted from the client, so a client can't claim an edit
    didn't happen and bypass the regeneration edit-preservation rule (see
    app/repositories/roadmap_repository.py's docstrings)."""

    def __init__(
        self,
        db: Session,
        roadmap_repository: RoadmapRepository | None = None,
    ) -> None:
        self.db = db
        self.roadmap_repository = roadmap_repository or RoadmapRepository(db)

    def update_item(
        self,
        *,
        item_id: int,
        user_id: int,
        title: str | None,
        description: str | None,
    ) -> RoadmapItem:
        item = self.roadmap_repository.get_item_owned(item_id=item_id, user_id=user_id)
        if item is None:
            raise RoadmapItemNotFoundError("Roadmap item not found.")

        return self.roadmap_repository.update_item(
            item, title=title, description=description
        )
