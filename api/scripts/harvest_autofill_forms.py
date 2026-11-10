import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
from lxml import html

SOURCES = {
    "google_otgs": "https://docs.google.com/forms/d/e/1FAIpQLSddKFrCTp3gYD6nU8faR6NJU-ER5Sr_mctzzLWER6sZzSY6YA/viewform",
    "google_teaching": "https://docs.google.com/forms/d/e/1FAIpQLSfycIw9fZGftztw3-w0NApkrWM5D_LtAI0xeRX_w20BKsk5Ag/viewform",
    "greenhouse_verisign": "https://job-boards.greenhouse.io/verisign/jobs/4403206003",
    "lever_mashgin": "https://jobs.lever.co/mashgin/f82e7b37-9e91-416e-97b6-64449ab28f48/apply",
    "grant_magic": "https://form.jotform.com/222414405256044",
    "grant_afnet": "https://form.jotform.com/250166730672153",
}


def text(element):
    return " ".join(element.text_content().split()).strip(" *✱")


def google_fields(content):
    data = json.loads(
        re.search(r"FB_PUBLIC_LOAD_DATA_ = (.*?);</script>", content, re.DOTALL)[1]
    )
    fields = []
    section = ""
    for row in data[1][1]:
        if not row[1]:
            continue
        if row[3] in {6, 8}:
            section = row[1]
            continue
        if row[3] not in {0, 1, 2, 3, 4}:
            continue
        entry = row[4][0]
        kind = {0: "text", 1: "text", 2: "radio", 3: "select", 4: "checkbox"}[row[3]]
        fields.append(
            {
                "key": str(row[0]),
                "label": row[1].strip(),
                "tag": "textarea"
                if row[3] == 1
                else "select"
                if kind == "select"
                else "input",
                "type": kind,
                "name": f"entry.{entry[0]}",
                "section": section,
                "help_text": row[2] or "",
                "required": bool(entry[2]),
                "options": [
                    {"label": option[0], "value": option[0]}
                    for option in entry[1] or []
                ]
                if kind in {"radio", "select", "checkbox"}
                else [],
            }
        )
    return fields


def html_fields(content):
    tree = html.fromstring(content)
    fields = []
    seen = set()
    for element in tree.xpath("//input|//textarea|//select"):
        kind = element.get("type", "text").lower()
        name, identifier = element.get("name", ""), element.get("id", "")
        if kind in {"hidden", "submit", "button"} or not (name or identifier):
            continue
        if identifier == "input_language":
            continue
        labels = (
            tree.xpath("//label[@for=$identifier]", identifier=identifier)
            if identifier
            else []
        )
        group = element.xpath(
            "ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' application-question ') or contains(concat(' ', normalize-space(@class), ' '), ' form-line ')][1]"
        )
        section = ""
        if group:
            primary = group[0].xpath(
                ".//*[contains(concat(' ', normalize-space(@class), ' '), ' application-label ') or contains(concat(' ', normalize-space(@class), ' '), ' form-label ')]"
            )
            section = text(primary[0]) if primary else ""
        label_element = (
            labels[-1]
            if len(labels) > 1 and name.endswith("]")
            else labels[0]
            if labels
            else None
        )
        label = element.get("aria-label") or (
            text(label_element) if label_element is not None else section
        )
        if "@" in label and section:
            label = section
        if label in {"Attach", "Enter manually"}:
            label = {"resume": "Resume/CV", "cover_letter": "Cover Letter"}.get(
                identifier, label
            )
        if not label:
            continue
        options = []
        if kind in {"radio", "checkbox"} and name:
            if name in seen:
                continue
            seen.add(name)
            choices = tree.xpath("//input[@name=$name]", name=name)
            for choice in choices:
                parents = choice.xpath("ancestor::label[1]")
                choice_labels = tree.xpath(
                    "//label[@for=$identifier]", identifier=choice.get("id", "")
                )
                choice_label = (
                    text((parents or choice_labels)[0])
                    if parents or choice_labels
                    else ""
                )
                if choice_label:
                    options.append(
                        {"label": choice_label, "value": choice.get("value", "")}
                    )
            label = section or label
        if element.tag == "select":
            options = [
                {"label": text(option), "value": option.get("value", text(option))}
                for option in element.xpath("./option")
                if option.get("value", text(option))
            ]
        fields.append(
            {
                "key": identifier or name,
                "tag": element.tag,
                "type": kind if element.tag != "select" else "select",
                "name": name,
                "id": identifier,
                "label": label,
                "section": section if section != label else "",
                "placeholder": element.get("placeholder", ""),
                "help_text": text(labels[-1])
                if len(labels) > 1 and label_element is labels[0]
                else "",
                "autocomplete": element.get("autocomplete", ""),
                "required": element.get("required") is not None
                or element.get("aria-required") == "true",
                "options": options,
                "accept": element.get("accept", ""),
            }
        )
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/autofill-public-descriptors")
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for name, url in SOURCES.items():
            response = client.get(url)
            response.raise_for_status()
            fields = (
                google_fields(response.text)
                if name.startswith("google_")
                else html_fields(response.text)
            )
            if not fields:
                raise ValueError(f"No public descriptors found for {name}")
            result = {
                "name": f"public_{name}",
                "source": {
                    "url": url,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "method": "public GET; field descriptors only",
                },
                "fields": fields,
            }
            (args.output / f"public_{name}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            print(f"{name}: {len(fields)} descriptors")


if __name__ == "__main__":
    main()
