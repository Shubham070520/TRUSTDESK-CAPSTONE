from typing import Iterator
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app import Application
from app.common.exceptions import DatabaseError, NotFoundError
from app.helper.base import BaseHelper
from app.models.base import Base
from tests.base import ApiTestCase
from tests.widget_model import Widget


class TestBaseModelAndHelper(ApiTestCase):
    @pytest.fixture()
    def session(self, application: Application) -> Iterator[Session]:
        application.database.create_tables(Base.metadata)
        with application.database.session_scope() as db:
            yield db

    @pytest.fixture()
    def helper(self, session: Session) -> BaseHelper:
        return BaseHelper(session)

    def _add(self, helper: BaseHelper, name: str) -> Widget:
        widget = Widget(name=name)
        helper.db.add(widget)
        helper.commit()
        return widget

    def test_table_name_uses_prefix(self) -> None:
        assert Widget.__tablename__ == "td_widget"

    def test_model_defaults(self, helper: BaseHelper) -> None:
        widget = self._add(helper, "w1")
        assert isinstance(widget.id, int)
        assert len(widget.uuid) == 36
        assert widget.is_deleted is False
        assert widget.created_at is not None
        assert widget.updated_at is not None

    def test_uuids_are_unique(self, helper: BaseHelper) -> None:
        a, b = self._add(helper, "a"), self._add(helper, "b")
        assert a.uuid != b.uuid

    def test_get_by_uuid(self, helper: BaseHelper) -> None:
        widget = self._add(helper, "w1")
        assert helper.get_by_uuid(Widget, widget.uuid).id == widget.id

    def test_get_by_uuid_missing(self, helper: BaseHelper) -> None:
        with pytest.raises(NotFoundError):
            helper.get_by_uuid(Widget, str(uuid4()))

    def test_soft_delete_hides_row_but_keeps_it(self, helper: BaseHelper) -> None:
        widget = self._add(helper, "w1")
        helper.soft_delete(widget)
        assert widget.is_deleted is True
        with pytest.raises(NotFoundError):
            helper.get_by_uuid(Widget, widget.uuid)

    def test_commit_failure_rolls_back_and_raises(self, helper: BaseHelper) -> None:
        self._add(helper, "dup")
        helper.db.add(Widget(name="dup"))
        with pytest.raises(DatabaseError):
            helper.commit()
        # Session is usable again after the rollback.
        self._add(helper, "after")
