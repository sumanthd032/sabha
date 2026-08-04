"""Seed data for jurisdiction routing: a hand curated subset of the
Allocation of Business Rules relevant to the platform and gig work
consultation, plus the loader that embeds and persists it.

This is not exhaustive, and it is not meant to be. Real gig and
platform work regulation spans several ministries whose own mandates
were never written with platform work in mind, which is exactly why
section 6.5 treats routing as a retrieval problem with a checkable
citation rather than a guess: a clause with no confident match among
these entries is meant to reach the human queue, not be forced onto
the nearest one.

Every citation below is a real legal instrument. The three Code on
Social Security, 2020 entries are the first Indian statute to define
gig and platform work; the Allocation of Business Rules entries are
drawn from the Second Schedule as published by the Cabinet Secretariat.
"""

from dataclasses import dataclass

from sqlmodel import Session, select

from sabha.llm.client import GenaiClient, call_embedding
from sabha.models import AllocationRule
from sabha.services.quota import QuotaGuard


@dataclass(frozen=True)
class AllocationRuleSeed:
    department: str
    citation: str
    mandate_text: str


ALLOCATION_RULES: tuple[AllocationRuleSeed, ...] = (
    AllocationRuleSeed(
        department="Ministry of Labour and Employment",
        citation="Code on Social Security, 2020 (Act 36 of 2020), section 2(61)",
        mandate_text=(
            "Defines a platform worker as a person engaged in or undertaking "
            "platform work, meaning work arising out of access to an "
            "organisation or individual through an online platform, outside "
            "a traditional employer-employee relationship, in exchange for "
            "payment."
        ),
    ),
    AllocationRuleSeed(
        department="Ministry of Labour and Employment",
        citation="Code on Social Security, 2020, section 2(35)",
        mandate_text=(
            "Defines a gig worker as a person who performs work outside a "
            "traditional employer-employee relationship and earns from such "
            "activities."
        ),
    ),
    AllocationRuleSeed(
        department="Ministry of Labour and Employment",
        citation="Code on Social Security, 2020, sections 113 to 114 and Schedule VII",
        mandate_text=(
            "Extends social security schemes to gig and platform workers, "
            "funded in part by a contribution from aggregators. Schedule VII "
            "lists the aggregator categories covered, including ride "
            "sharing, food and grocery delivery, and e-marketplace services."
        ),
    ),
    AllocationRuleSeed(
        department="Ministry of Labour and Employment",
        citation="Code on Wages, 2019 and Industrial Relations Code, 2020",
        mandate_text=(
            "Governs minimum wages, timely payment, and dispute resolution "
            "machinery for the workforce generally, extended to platform "
            "mediated work only where an employer-employee relationship is "
            "found to exist."
        ),
    ),
    AllocationRuleSeed(
        department="Ministry of Electronics and Information Technology",
        citation="Allocation of Business Rules, 1961, Second Schedule, entry 1",
        mandate_text=(
            "Policy matters relating to information technology, "
            "electronics, and the internet."
        ),
    ),
    AllocationRuleSeed(
        department="Ministry of Electronics and Information Technology",
        citation="Allocation of Business Rules, 1961, Second Schedule, entry 2",
        mandate_text="Promotion of internet, IT, and IT enabled services.",
    ),
    AllocationRuleSeed(
        department="Ministry of Electronics and Information Technology",
        citation="Allocation of Business Rules, 1961, Second Schedule, entry 2A",
        mandate_text="Promotion of digital transactions, including digital payments.",
    ),
    AllocationRuleSeed(
        department="Ministry of Electronics and Information Technology",
        citation=(
            "Information Technology Act, 2000 and the Information Technology "
            "(Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021"
        ),
        mandate_text=(
            "Due diligence obligations for intermediaries and digital "
            "platforms, including grievance redress timelines, applicable "
            "to platforms that mediate gig and platform work."
        ),
    ),
    AllocationRuleSeed(
        department="Department for Promotion of Industry and Internal Trade",
        citation="Allocation of Business Rules, 1961, Second Schedule, entry 4B",
        mandate_text="Promotion of internal trade, including retail trade.",
    ),
    AllocationRuleSeed(
        department="Department for Promotion of Industry and Internal Trade",
        citation="Allocation of Business Rules, 1961, Second Schedule, entry 4C",
        mandate_text="Welfare of traders and their employees.",
    ),
    AllocationRuleSeed(
        department="Department for Promotion of Industry and Internal Trade",
        citation="Allocation of Business Rules, 1961, Second Schedule, entry 4E",
        mandate_text="Matters relating to start-ups.",
    ),
    AllocationRuleSeed(
        department="Department of Consumer Affairs",
        citation=(
            "Allocation of Business Rules, 1961, Second Schedule, Department "
            "of Consumer Affairs, entry 15, read with the Consumer "
            "Protection Act, 2019"
        ),
        mandate_text=(
            "Consumer protection against unfair trade practices, including "
            "obligations placed on e-commerce entities and marketplace "
            "platforms under the Consumer Protection (E-Commerce) Rules, "
            "2020."
        ),
    ),
)


def load_allocation_rules(
    session: Session,
    quota: QuotaGuard,
    genai_client: GenaiClient | None = None,
) -> int:
    """Insert every rule not already present, embedding its mandate text.

    Matched by (department, citation): rerunning this after the table
    already carries a rule for that pair makes no embedding call for
    it, and a full reload after clearing the table still makes no
    repeat network call, since call_embedding caches by content hash
    underneath this.

    Returns the number of rows actually inserted.
    """
    existing = {
        (rule.department, rule.citation) for rule in session.exec(select(AllocationRule)).all()
    }
    inserted = 0
    for seed in ALLOCATION_RULES:
        if (seed.department, seed.citation) in existing:
            continue
        vector = call_embedding(session, quota, seed.mandate_text, genai_client=genai_client)
        session.add(
            AllocationRule(
                department=seed.department,
                citation=seed.citation,
                mandate_text=seed.mandate_text,
                embedding=vector,
            )
        )
        inserted += 1
    session.commit()
    return inserted
