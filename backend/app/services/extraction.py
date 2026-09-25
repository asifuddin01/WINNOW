"""Data extraction (guide 8.12) on `app.extraction`'s forms.

Forms are built by owners and admins and published before anyone extracts with them;
a published version is locked, and a change starts the next version (its entries stay
with the version they were made on). Each person extracts a study on their own, blinded
like screening; with dual extraction, someone who resolves conflicts turns two entries
into one consensus.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import extraction
from app.models import (
    EntryStatus,
    ExtractionConsensus,
    ExtractionEntry,
    ExtractionForm,
    FullTextStatus,
    Record,
    User,
)
from app.models.base import uuid7
from app.schemas.extraction import (
    ConsensusIn,
    ConsensusOut,
    ConsensusView,
    DifferenceOut,
    EntryIn,
    EntryOut,
    FormIn,
    FormOut,
    FormPatch,
    RecordExtraction,
    StudyExtraction,
)
from app.security.permissions import Capability, ProjectAccess
from app.services import audit
from app.services.audit import Actor
from app.services.blinding import sees_others
from app.services.errors import ConflictError, DomainError, ForbiddenError, NotFoundError

MAX_STUDIES = 5_000
DONE = (EntryStatus.SUBMITTED, EntryStatus.VERIFIED)


class InvalidFormError(DomainError):
    status = 422
    code = "invalid_form"


class InvalidEntryError(DomainError):
    status = 422
    code = "invalid_entry"


def study_label(authors: list[str], year: int | None, title: str | None) -> str:
    """ "Smith 2019", or the start of the title when there is no author."""
    if authors:
        first = authors[0].strip()
        surname = first.split(",")[0].strip() if "," in first else first.rsplit(" ", 1)[-1]
        return f"{surname} {year}" if year else surname
    return (title or "Untitled")[:40]


def checked_schema(raw: dict[str, Any]) -> extraction.FormSchema:
    try:
        return extraction.parse_schema(raw)
    except extraction.SchemaError as error:
        raise InvalidFormError(
            "The form has problems: " + " ".join(error.problems[:5]), problems=error.problems
        ) from error


def value_at(data: dict[str, Any], path: str) -> Any:
    """`key`, or `key[row].column` in a table."""
    if "[" not in path:
        return data.get(path)
    key, _, rest = path.partition("[")
    row, _, column = rest.partition("].")
    rows = data.get(key) or []
    index = int(row) - 1
    return rows[index].get(column) if index < len(rows) else None


class ExtractionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- Forms --------------------------------------------------------------------

    async def forms(self, access: ProjectAccess) -> list[FormOut]:
        entries = dict(
            (
                await self._db.execute(
                    select(ExtractionEntry.form_id, func.count())
                    .where(ExtractionEntry.project_id == access.project_id)
                    .group_by(ExtractionEntry.form_id)
                )
            )
            .tuples()
            .all()
        )
        rows = list(
            await self._db.scalars(
                select(ExtractionForm)
                .where(ExtractionForm.project_id == access.project_id)
                .order_by(ExtractionForm.created_at, ExtractionForm.version)
            )
        )
        newest: dict[uuid.UUID, int] = {}
        for row in rows:
            newest[row.family_id] = max(newest.get(row.family_id, 0), row.version)
        return [_form_out(row, entries.get(row.id, 0), newest[row.family_id]) for row in rows]

    async def create_form(self, access: ProjectAccess, body: FormIn, actor: Actor) -> FormOut:
        self._may_build(access)
        schema = extraction.schema_to_json(checked_schema(body.schema_))
        form_id = uuid7()
        form = ExtractionForm(
            id=form_id,
            project_id=access.project_id,
            family_id=form_id,
            name=body.name,
            version=1,
            schema=schema,
            dual=body.dual,
            created_by=access.user.id,
        )
        self._db.add(form)
        self._audit(access, actor, "extraction.form_created", form)
        await self._db.commit()
        await self._db.refresh(form)
        return _form_out(form, 0, 1)

    async def update_form(
        self, access: ProjectAccess, form_id: uuid.UUID, body: FormPatch, actor: Actor
    ) -> FormOut:
        self._may_build(access)
        form = await self._form(access, form_id)
        if form.published:
            raise ConflictError("A published form is locked. Start a new version to change it.")
        if body.name is not None:
            form.name = body.name
        if body.schema_ is not None:
            form.schema = extraction.schema_to_json(checked_schema(body.schema_))
        if body.dual is not None:
            form.dual = body.dual
        self._audit(access, actor, "extraction.form_updated", form)
        await self._db.commit()
        await self._db.refresh(form)
        return _form_out(form, 0, form.version)

    async def publish(self, access: ProjectAccess, form_id: uuid.UUID, actor: Actor) -> FormOut:
        self._may_build(access)
        form = await self._form(access, form_id)
        if form.published:
            raise ConflictError("This version is already published.")
        if not checked_schema(form.schema).values():
            raise InvalidFormError("Add at least one field that holds a value before publishing.")
        form.published = True
        form.published_at = datetime.now(UTC)
        self._audit(access, actor, "extraction.form_published", form)
        await self._db.commit()
        await self._db.refresh(form)
        return _form_out(form, 0, form.version)

    async def new_version(self, access: ProjectAccess, form_id: uuid.UUID, actor: Actor) -> FormOut:
        """The next version of a published form, a draft starting from the newest one."""
        self._may_build(access)
        form = await self._form(access, form_id)
        versions = list(
            await self._db.scalars(
                select(ExtractionForm)
                .where(ExtractionForm.family_id == form.family_id)
                .order_by(ExtractionForm.version.desc())
            )
        )
        newest = versions[0]
        if not newest.published:
            raise ConflictError(f"Version {newest.version} is still a draft: change that one.")
        draft = ExtractionForm(
            id=uuid7(),
            project_id=access.project_id,
            family_id=form.family_id,
            name=newest.name,
            version=newest.version + 1,
            schema=newest.schema,
            dual=newest.dual,
            created_by=access.user.id,
        )
        self._db.add(draft)
        self._audit(access, actor, "extraction.form_versioned", draft)
        await self._db.commit()
        await self._db.refresh(draft)
        return _form_out(draft, 0, draft.version)

    async def delete_form(self, access: ProjectAccess, form_id: uuid.UUID, actor: Actor) -> None:
        self._may_build(access)
        form = await self._form(access, form_id)
        if form.published:
            raise ConflictError("A published form keeps the data extracted with it; it stays.")
        self._audit(access, actor, "extraction.form_deleted", form)
        await self._db.delete(form)
        await self._db.commit()

    # --- Entries ------------------------------------------------------------------

    async def studies(self, access: ProjectAccess, form_id: uuid.UUID) -> list[StudyExtraction]:
        form = await self._form(access, form_id)
        others = sees_others(access)
        per_record = (
            select(
                ExtractionEntry.record_id,
                func.max(ExtractionEntry.status)
                .filter(ExtractionEntry.user_id == access.user.id)
                .label("mine"),
                func.count().filter(ExtractionEntry.status.in_(DONE)).label("done"),
            )
            .where(ExtractionEntry.form_id == form.id)
            .group_by(ExtractionEntry.record_id)
            .subquery()
        )
        agreed = (
            select(ExtractionConsensus.record_id)
            .where(ExtractionConsensus.form_id == form.id)
            .subquery()
        )
        rows = await self._db.execute(
            select(
                Record.id,
                Record.authors,
                Record.year,
                Record.title,
                per_record.c.mine,
                per_record.c.done,
                agreed.c.record_id,
            )
            .outerjoin(per_record, per_record.c.record_id == Record.id)
            .outerjoin(agreed, agreed.c.record_id == Record.id)
            .where(
                Record.project_id == access.project_id,
                Record.ft_final == FullTextStatus.INCLUDED,
                Record.is_duplicate.is_(False),
            )
            .order_by(Record.year.nulls_last(), Record.id)
            .limit(MAX_STUDIES)
        )
        return [
            StudyExtraction(
                record_id=record_id,
                label=study_label(authors, year, title),
                title=title,
                mine="none" if mine is None else EntryStatus(mine).value,
                submitted=(done or 0) if others else None,
                consensus=(consensus is not None) if others else None,
            )
            for record_id, authors, year, title, mine, done, consensus in rows
        ]

    async def record(
        self, access: ProjectAccess, form_id: uuid.UUID, record_id: uuid.UUID
    ) -> RecordExtraction:
        form = await self._form(access, form_id)
        record = await self._included(access, record_id)
        others = sees_others(access)
        entries = await self._entries(access, form, record.id, mine_only=not others)
        consensus = await self._consensus(form, record.id) if others else None
        return RecordExtraction(
            record_id=record.id,
            title=record.title,
            label=study_label(record.authors, record.year, record.title),
            entries=entries,
            consensus=consensus,
        )

    async def save_entry(
        self,
        access: ProjectAccess,
        form_id: uuid.UUID,
        record_id: uuid.UUID,
        body: EntryIn,
        actor: Actor,
    ) -> EntryOut:
        form = await self._form(access, form_id)
        if not form.published:
            raise ConflictError("This form is still a draft; it can be used once it is published.")
        record = await self._included(access, record_id)
        status = EntryStatus(body.status)
        try:
            data = extraction.validate_entry(
                checked_schema(form.schema), body.data, complete=status is EntryStatus.SUBMITTED
            )
        except extraction.EntryError as error:
            raise InvalidEntryError(
                "Some values need attention.", problems=error.problems
            ) from error
        saved = (
            await self._db.execute(
                insert(ExtractionEntry)
                .values(
                    id=uuid7(),
                    project_id=access.project_id,
                    form_id=form.id,
                    record_id=record.id,
                    user_id=access.user.id,
                    data=data,
                    status=status,
                )
                .on_conflict_do_update(
                    index_elements=[
                        ExtractionEntry.form_id,
                        ExtractionEntry.record_id,
                        ExtractionEntry.user_id,
                    ],
                    # A changed entry is no longer the one a consensus reconciled.
                    set_={"data": data, "status": status, "updated_at": func.now()},
                )
                .returning(ExtractionEntry)
            )
        ).scalar_one()
        audit.record(
            self._db,
            "extraction.saved",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"form": str(form.id), "status": status.value},
        )
        await self._db.commit()
        await self._db.refresh(saved)
        return _entry_out(saved, access.user.name, access.user.id)

    # --- Consensus ----------------------------------------------------------------

    async def consensus_view(
        self, access: ProjectAccess, form_id: uuid.UUID, record_id: uuid.UUID
    ) -> ConsensusView:
        self._may_resolve(access)
        form = await self._form(access, form_id)
        record = await self._included(access, record_id)
        schema = checked_schema(form.schema)
        entries = [
            entry
            for entry in await self._entries(access, form, record.id, mine_only=False)
            if entry.status in DONE
        ]
        paths: list[tuple[str, str]] = []
        for other in entries[1:]:
            for difference in extraction.differences(schema, entries[0].data, other.data):
                if (difference.path, difference.label) not in paths:
                    paths.append((difference.path, difference.label))
        agreed = dict(entries[0].data) if entries else {}
        for path, _ in paths:
            agreed.pop(path.partition("[")[0], None)
        return ConsensusView(
            record_id=record.id,
            title=record.title,
            label=study_label(record.authors, record.year, record.title),
            entries=entries,
            differences=[
                DifferenceOut(
                    path=path, label=label, values=[value_at(e.data, path) for e in entries]
                )
                for path, label in paths
            ],
            agreed=agreed,
            consensus=await self._consensus(form, record.id),
        )

    async def save_consensus(
        self,
        access: ProjectAccess,
        form_id: uuid.UUID,
        record_id: uuid.UUID,
        body: ConsensusIn,
        actor: Actor,
    ) -> ConsensusOut:
        self._may_resolve(access)
        form = await self._form(access, form_id)
        record = await self._included(access, record_id)
        try:
            data = extraction.validate_entry(checked_schema(form.schema), body.data, complete=True)
        except extraction.EntryError as error:
            raise InvalidEntryError(
                "Some values need attention.", problems=error.problems
            ) from error
        saved = (
            await self._db.execute(
                insert(ExtractionConsensus)
                .values(
                    id=uuid7(),
                    project_id=access.project_id,
                    form_id=form.id,
                    record_id=record.id,
                    data=data,
                    resolved_by=access.user.id,
                )
                .on_conflict_do_update(
                    index_elements=[ExtractionConsensus.form_id, ExtractionConsensus.record_id],
                    set_={"data": data, "resolved_by": access.user.id, "updated_at": func.now()},
                )
                .returning(ExtractionConsensus)
            )
        ).scalar_one()
        # The entries it reconciled are verified.
        await self._db.execute(
            update(ExtractionEntry)
            .where(
                ExtractionEntry.form_id == form.id,
                ExtractionEntry.record_id == record.id,
                ExtractionEntry.status == EntryStatus.SUBMITTED,
            )
            .values(status=EntryStatus.VERIFIED)
        )
        audit.record(
            self._db,
            "extraction.consensus_saved",
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="record",
            entity_id=record.id,
            after={"form": str(form.id)},
        )
        await self._db.commit()
        await self._db.refresh(saved)
        return ConsensusOut(
            data=saved.data, resolved_by=access.user.name, updated_at=saved.updated_at
        )

    # --- Helpers ------------------------------------------------------------------

    def _may_build(self, access: ProjectAccess) -> None:
        if not access.can(Capability.EDIT_SETUP):
            raise ForbiddenError("Only owners and admins build extraction forms.")

    def _may_resolve(self, access: ProjectAccess) -> None:
        if not access.can(Capability.RESOLVE_CONFLICTS):
            raise ForbiddenError("Only those who resolve conflicts reconcile extractions.")

    async def _form(self, access: ProjectAccess, form_id: uuid.UUID) -> ExtractionForm:
        form = await self._db.scalar(
            select(ExtractionForm).where(
                ExtractionForm.id == form_id, ExtractionForm.project_id == access.project_id
            )
        )
        if form is None:
            raise NotFoundError("That form is not in this review.")
        return form

    async def _included(self, access: ProjectAccess, record_id: uuid.UUID) -> Record:
        """Data is extracted from studies included at full text."""
        record = await self._db.scalar(
            select(Record).where(
                Record.id == record_id,
                Record.project_id == access.project_id,
                Record.is_duplicate.is_(False),
            )
        )
        if record is None:
            raise NotFoundError("That record is not in this review.")
        if record.ft_final is not FullTextStatus.INCLUDED:
            raise ConflictError("Data is extracted from studies included at full text.")
        return record

    async def _entries(
        self, access: ProjectAccess, form: ExtractionForm, record_id: uuid.UUID, *, mine_only: bool
    ) -> list[EntryOut]:
        statement = (
            select(ExtractionEntry, User.name)
            .outerjoin(User, User.id == ExtractionEntry.user_id)
            .where(ExtractionEntry.form_id == form.id, ExtractionEntry.record_id == record_id)
            .order_by(ExtractionEntry.created_at)
        )
        if mine_only:
            statement = statement.where(ExtractionEntry.user_id == access.user.id)
        return [
            _entry_out(row, name, access.user.id) for row, name in await self._db.execute(statement)
        ]

    async def _consensus(self, form: ExtractionForm, record_id: uuid.UUID) -> ConsensusOut | None:
        row = await self._db.execute(
            select(ExtractionConsensus, User.name)
            .outerjoin(User, User.id == ExtractionConsensus.resolved_by)
            .where(
                ExtractionConsensus.form_id == form.id,
                ExtractionConsensus.record_id == record_id,
            )
        )
        found = row.first()
        if found is None:
            return None
        consensus, name = found
        return ConsensusOut(data=consensus.data, resolved_by=name, updated_at=consensus.updated_at)

    def _audit(
        self, access: ProjectAccess, actor: Actor, action: str, form: ExtractionForm
    ) -> None:
        audit.record(
            self._db,
            action,
            actor,
            user_id=access.user.id,
            project_id=access.project_id,
            entity_type="extraction_form",
            entity_id=form.id,
            after={"name": form.name, "version": form.version},
        )


def _form_out(row: ExtractionForm, entries: int, newest: int) -> FormOut:
    return FormOut(
        id=row.id,
        family_id=row.family_id,
        name=row.name,
        version=row.version,
        schema_=row.schema,
        dual=row.dual,
        published=row.published,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        entries=entries,
        latest=row.version == newest,
    )


def _entry_out(row: ExtractionEntry, extractor: str | None, me: uuid.UUID) -> EntryOut:
    return EntryOut(
        id=row.id,
        record_id=row.record_id,
        form_id=row.form_id,
        data=row.data,
        status=row.status,
        extractor=extractor,
        mine=row.user_id == me,
        updated_at=row.updated_at,
    )
