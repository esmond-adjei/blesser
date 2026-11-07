"""Global search for Gradis: case-insensitive substring match per kind, a
few hits each, always filtered by owner."""

from sqlalchemy import or_, select

from api.applications import models as application_models
from api.candidates import models as candidate_models
from api.core.db import like_pattern
from api.outreach import models as outreach_models
from api.prospects import models as prospect_models
from api.runs import models as run_models

KINDS = ("runs", "schools", "programs", "professors", "candidates", "applications", "drafts", "documents", "papers")
PER_KIND = 5
_SNIPPET = 160


def _snip(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= _SNIPPET else text[:_SNIPPET] + "…"


async def search_everything(
    session, user_id: str, query: str, kinds: list[str] | None = None, limit: int = PER_KIND
) -> dict:
    q = (query or "").strip()
    if len(q) < 2:
        return {"error": "Give at least two characters to search for."}
    wanted = [k for k in (kinds or KINDS) if k in KINDS] or list(KINDS)
    pattern = like_pattern(q)
    limit = max(1, min(int(limit or PER_KIND), 10))
    out: dict[str, list] = {}

    if "runs" in wanted:
        r = run_models.Run
        rows = (
            await session.execute(
                select(r.id, r.field, r.region, r.status, r.interest_statement)
                .where(
                    r.user_id == user_id,
                    or_(r.field.ilike(pattern), r.region.ilike(pattern), r.interest_statement.ilike(pattern)),
                )
                .order_by(r.created_at.desc())
                .limit(limit)
            )
        ).all()
        out["runs"] = [
            {"id": i, "field": f, "region": g, "status": s, "interest": _snip(t)} for i, f, g, s, t in rows
        ]

    if "schools" in wanted:
        s = prospect_models.School
        rows = (
            await session.execute(
                select(s.id, s.name, s.country)
                .where(s.user_id == user_id, or_(s.name.ilike(pattern), s.country.ilike(pattern)))
                .order_by(s.name)
                .limit(limit)
            )
        ).all()
        out["schools"] = [{"id": i, "name": n, "country": c} for i, n, c in rows]

    if "programs" in wanted:
        p, s = prospect_models.Program, prospect_models.School
        rows = (
            await session.execute(
                select(p.id, p.name, s.id, s.name)
                .join(s, s.id == p.school_id)
                .where(p.user_id == user_id, or_(p.name.ilike(pattern), s.name.ilike(pattern)))
                .order_by(p.name)
                .limit(limit)
            )
        ).all()
        out["programs"] = [{"id": i, "name": n, "school_id": sid, "school": sn} for i, n, sid, sn in rows]

    if "professors" in wanted or "candidates" in wanted:
        f, p, s = prospect_models.Professor, prospect_models.Program, prospect_models.School
        prof_rows = (
            await session.execute(
                select(f.id, f.name, f.lab_name, p.name, s.name)
                .join(p, p.id == f.program_id)
                .join(s, s.id == p.school_id)
                .where(f.user_id == user_id, or_(f.name.ilike(pattern), f.lab_name.ilike(pattern), s.name.ilike(pattern), p.name.ilike(pattern)))
                .order_by(f.name)
                .limit(limit * 2)
            )
        ).all()
        if "professors" in wanted:
            out["professors"] = [
                {"id": i, "name": n, "lab": lab, "program": pn, "school": sn}
                for i, n, lab, pn, sn in prof_rows[:limit]
            ]
        if "candidates" in wanted:
            c = candidate_models.CandidateScore
            names = {i: (n, sn) for i, n, _lab, _pn, sn in prof_rows}
            rows = (
                await session.execute(
                    select(c.id, c.professor_id, c.run_id, c.status, c.similarity_score)
                    .where(c.user_id == user_id, c.professor_id.in_(list(names)))
                    .order_by(c.similarity_score.desc().nulls_last())
                    .limit(limit)
                )
            ).all() if names else []
            out["candidates"] = [
                {
                    "id": i,
                    "professor_id": pid,
                    "professor": names[pid][0],
                    "school": names[pid][1],
                    "run_id": rid,
                    "status": run_models.status_str(st),
                    "similarity_score": sc,
                }
                for i, pid, rid, st, sc in rows
            ]

    if "professors" in wanted:
        idx = prospect_models.ProfessorIndex
        indexed = (await session.execute(select(idx).where(
            idx.user_id == user_id,
            or_(idx.name.ilike(pattern), idx.school_name.ilike(pattern)),
        ).order_by(idx.name).limit(limit))).scalars().all()
        existing = {(r["name"].casefold(), r["school"].casefold()) for r in out["professors"]}
        out["professors"].extend(
            {"id": r.id, "name": r.name, "school": r.school_name, "program": r.program_name}
            for r in indexed if (r.name.casefold(), r.school_name.casefold()) not in existing
        )
        out["professors"] = out["professors"][:limit]

    if "documents" in wanted:
        from api.cv.models import CvDocument
        docs = (await session.execute(select(CvDocument).where(
            CvDocument.user_id == user_id,
            or_(CvDocument.title.ilike(pattern), CvDocument.markdown.ilike(pattern)),
        ).order_by(CvDocument.updated_at.desc()).limit(limit))).scalars().all()
        out["documents"] = [{"id": d.id, "title": d.title, "kind": d.kind} for d in docs]

    if "papers" in wanted:
        pa, f = prospect_models.Paper, prospect_models.Professor
        rows = (
            await session.execute(
                select(pa.id, pa.title, pa.year, pa.url, pa.abstract, f.id, f.name)
                .join(f, f.id == pa.professor_id)
                .where(pa.user_id == user_id, or_(pa.title.ilike(pattern), pa.abstract.ilike(pattern)))
                .order_by(pa.year.desc().nulls_last(), pa.title)
                .limit(limit)
            )
        ).all()
        out["papers"] = [
            {"id": i, "title": t, "year": y, "url": u, "abstract": _snip(a), "professor_id": pid, "professor": pn}
            for i, t, y, u, a, pid, pn in rows
        ]

    if "applications" in wanted:
        a = application_models.Application
        rows = (
            await session.execute(
                select(a.id, a.school, a.program, a.status, a.deadline)
                .where(
                    a.user_id == user_id,
                    or_(a.school.ilike(pattern), a.program.ilike(pattern), a.location.ilike(pattern), a.notes.ilike(pattern)),
                )
                .order_by(a.updated_at.desc())
                .limit(limit)
            )
        ).all()
        out["applications"] = [
            {"id": i, "school": sc, "program": pr, "status": st, "deadline": dl} for i, sc, pr, st, dl in rows
        ]

    if "drafts" in wanted:
        d = outreach_models.EmailDraft
        c = candidate_models.CandidateScore
        f = prospect_models.Professor
        rows = (
            await session.execute(
                select(d.id, d.candidate_id, d.subject, f.name)
                .join(c, c.id == d.candidate_id)
                .join(f, f.id == c.professor_id)
                .where(
                    d.user_id == user_id,
                    or_(d.subject.ilike(pattern), d.body.ilike(pattern), f.name.ilike(pattern)),
                )
                .order_by(d.created_at.desc())
                .limit(limit)
            )
        ).all()
        out["drafts"] = [
            {"id": i, "candidate_id": cid, "subject": subj, "professor": pn} for i, cid, subj, pn in rows
        ]

    total = sum(len(v) for v in out.values())
    return {"query": q, "total": total, **out}
