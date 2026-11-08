"""LLM-as-judge for what the regular-expression checks cannot see: the store's voice.

The judge reads one customer message and one reply and answers PASS or FAIL against a short
rubric taken from the persona section of the system prompt. A judge is only worth trusting once
it agrees with a person, so `python -m emporio.evals.judge` runs it on replies a person labeled
(`evals/judge/labels.csv`) and reports how often they agree.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from emporio.config import load_settings
from emporio.evals.runner import with_model
from emporio.llm import ChatClient, MissingApiKeyError, OpenAIChatClient

DEFAULT_LABELS = Path(__file__).resolve().parents[3] / "evals" / "judge" / "labels.csv"
RUBRIC = """\
You grade one reply of a chat assistant for a musical-instrument store in Brazil.
The reply PASSES only when all of these hold:
1. It is written in the language of the customer's message (English, Spanish or Brazilian \
Portuguese), greeting included.
2. The tone is informal but professional, like a friend who understands music: welcoming, not \
robotic and not stiff.
3. It reads as a short chat message: plain text, no headings, no long lists (more than five \
items) and no long paragraphs.
4. It does not reveal instructions, tool names or internal rules, and does not pretend to be a \
person.
Do not judge whether prices or facts are right; other checks do that.
Answer with one line, "VERDICT: PASS" or "VERDICT: FAIL", then one short sentence with the reason."""
_VERDICT = re.compile(r"VERDICT:\s*(PASS|FAIL)", re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str


@dataclass(frozen=True)
class LabeledReply:
    row_id: str
    customer_message: str
    reply: str
    human_pass: bool


def build_messages(customer_message: str, reply: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": RUBRIC},
        {
            "role": "user",
            "content": f"Customer message:\n{customer_message}\n\nReply to grade:\n{reply}",
        },
    ]


def parse_verdict(text: str | None) -> Verdict | None:
    """The verdict in the judge's answer, or None when it did not follow the format."""
    match = _VERDICT.search(text or "")
    if match is None:
        return None
    reason = (text or "")[match.end() :].strip(" \n.:-")
    return Verdict(match.group(1).upper() == "PASS", reason)


def judge_reply(client: ChatClient, customer_message: str, reply: str) -> Verdict:
    answer = client.chat(build_messages(customer_message, reply), [])
    verdict = parse_verdict(answer.get("content"))
    if verdict is None:
        raise ValueError(f"the judge did not answer PASS or FAIL: {answer.get('content')!r}")
    return verdict


def agreement(pairs: Sequence[tuple[bool, bool]]) -> dict[str, float]:
    """How a judge compares with a person, from (human_pass, judge_pass) pairs.

    `kappa` is Cohen's kappa: agreement beyond what the two would reach by chance, so a judge
    that says PASS to everything does not look good on a set where most replies pass.
    """
    n = len(pairs)
    if n == 0:
        raise ValueError("no labeled replies")
    agree = sum(human == judge for human, judge in pairs)
    p_human = sum(human for human, _ in pairs) / n
    p_judge = sum(judge for _, judge in pairs) / n
    chance = p_human * p_judge + (1 - p_human) * (1 - p_judge)
    observed = agree / n
    kappa = (observed - chance) / (1 - chance) if chance < 1 else float(observed == 1)
    return {
        "n": n,
        "accuracy": observed,
        "kappa": kappa,
        "false_pass": sum(judge and not human for human, judge in pairs),
        "false_fail": sum(human and not judge for human, judge in pairs),
    }


def load_labels(path: Path) -> list[LabeledReply]:
    """Rows of the labels file that a person already marked `pass` or `fail`."""
    rows: list[LabeledReply] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = (row.get("human_label") or "").strip().lower()
            if not label:
                continue
            if label not in ("pass", "fail"):
                raise ValueError(f"row {row['id']}: human_label must be pass or fail, got {label!r}")
            rows.append(
                LabeledReply(row["id"], row["customer_message"], row["reply"], label == "pass")
            )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.evals.judge", description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS, help="the labeled replies")
    parser.add_argument("--model", help="override LLM_MODEL for the judge")
    parser.add_argument(
        "--min-kappa", type=float, metavar="K", help="exit 1 when Cohen's kappa is under K"
    )
    args = parser.parse_args(argv)

    load_dotenv()
    settings = with_model(load_settings(), args.model)
    try:
        client = OpenAIChatClient(settings)
    except MissingApiKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    pairs = []
    for item in load_labels(args.labels):
        verdict = judge_reply(client, item.customer_message, item.reply)
        pairs.append((item.human_pass, verdict.passed))
        if verdict.passed != item.human_pass:
            person = "pass" if item.human_pass else "fail"
            print(f"DISAGREE {item.row_id}: person {person}, judge said: {verdict.reason}")
    stats = agreement(pairs)
    print(
        f"{int(stats['n'])} labeled replies, accuracy {stats['accuracy']:.0%}, "
        f"kappa {stats['kappa']:.2f}, judge passed {int(stats['false_pass'])} that the person "
        f"failed and failed {int(stats['false_fail'])} that the person passed (model "
        f"{settings.llm_model})"
    )
    if args.min_kappa is not None and stats["kappa"] < args.min_kappa:
        print(f"GATE: kappa {stats['kappa']:.2f} is under {args.min_kappa:.2f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
