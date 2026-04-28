"""Smart follow-up sequence service with AI personalization.

Automatically generates and schedules personalized follow-ups based on:
- Lead engagement signals (opens, clicks, replies)
- Time since last contact
- Lead score and tier
- Industry best practices
- Previous conversation context
"""

import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
import logging

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FollowupTemplate:
    """Follow-up email template."""
    day: int  # Day in sequence (0, 3, 7, 14, 21)
    name: str  # Template name
    subject: str  # Email subject
    body: str  # Email body template
    channel: str  # email or whatsapp
    purpose: str  # value_add, social_proof, check_in, breakup
    variables: List[str]  # Required template variables


@dataclass
class FollowupSequence:
    """Complete follow-up sequence for a lead."""
    lead_id: str
    sequence_name: str
    started_at: str
    current_day: int
    next_followup_at: str
    total_followups: int
    completed_followups: int
    status: str  # active, paused, completed
    templates: List[FollowupTemplate]


class FollowupService:
    """Smart follow-up sequence generator and manager."""

    # Default follow-up sequence (proven to maximize replies)
    DEFAULT_SEQUENCE = [
        FollowupTemplate(
            day=0,
            name="Initial Outreach",
            subject="Partnership Opportunity with {company_name}",
            body="""Hi {contact_name},

I noticed {company_name} is {pain_point}. We've helped similar companies in {industry} achieve {result}.

Would you be open to a quick 15-min call to explore how we can help?

Best regards,
{sender_name}""",
            channel="email",
            purpose="value_proposition",
            variables=["company_name", "contact_name", "pain_point", "industry", "result", "sender_name"]
        ),
        FollowupTemplate(
            day=3,
            name="Value Add - Case Study",
            subject="How {similar_company} increased {metric} by {percentage}%",
            body="""Hi {contact_name},

Following up on my previous email. I thought you might find this interesting:

{similar_company} (similar to {company_name}) used our service to:
- {result_1}
- {result_2}
- {result_3}

Would love to share how we can achieve similar results for {company_name}.

Best,
{sender_name}""",
            channel="email",
            purpose="value_add",
            variables=["contact_name", "similar_company", "metric", "percentage", "company_name", "result_1", "result_2", "result_3", "sender_name"]
        ),
        FollowupTemplate(
            day=7,
            name="Friendly Check-in",
            subject="Quick question, {contact_name}",
            body="""Hi {contact_name},

Just checking in - did you get a chance to review my previous email?

I know you're busy, so I'll keep this brief. We help {industry} companies like {company_name} {value_proposition}.

Worth a quick chat?

Best,
{sender_name}""",
            channel="whatsapp",
            purpose="check_in",
            variables=["contact_name", "industry", "company_name", "value_proposition", "sender_name"]
        ),
        FollowupTemplate(
            day=14,
            name="Social Proof",
            subject="{industry} companies trust us",
            body="""Hi {contact_name},

I wanted to share some quick wins from our clients in {industry}:

✓ {client_1}: {result_1}
✓ {client_2}: {result_2}
✓ {client_3}: {result_3}

These companies saw results within {timeframe}. {company_name} could too.

Still interested in learning more?

Best,
{sender_name}""",
            channel="email",
            purpose="social_proof",
            variables=["contact_name", "industry", "client_1", "result_1", "client_2", "result_2", "client_3", "result_3", "timeframe", "company_name", "sender_name"]
        ),
        FollowupTemplate(
            day=21,
            name="Breakup Email",
            subject="Should I close your file?",
            body="""Hi {contact_name},

I haven't heard back, so I'm assuming now isn't the right time for {company_name}.

I'll stop reaching out, but feel free to contact me if:
- Your priorities change
- You want to revisit this later
- You have any questions

No hard feelings!

Best regards,
{sender_name}""",
            channel="email",
            purpose="breakup",
            variables=["contact_name", "company_name", "sender_name"]
        ),
    ]

    def __init__(self, config: Settings):
        self.config = config
        # self.generator = GeneratorService(config)
        self.followups_dir = Path(config.database.data_dir) / "followups"
        self.followups_dir.mkdir(parents=True, exist_ok=True)

    def generate_sequence(self, lead_data: Dict) -> FollowupSequence:
        """Generate personalized follow-up sequence for a lead."""
        sequence = FollowupSequence(
            lead_id=lead_data.get("id", ""),
            sequence_name="Smart Follow-up Sequence",
            started_at=datetime.now(timezone.utc).isoformat(),
            current_day=0,
            next_followup_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            total_followups=len(self.DEFAULT_SEQUENCE),
            completed_followups=0,
            status="active",
            templates=self.DEFAULT_SEQUENCE.copy()
        )

        # Personalize templates with lead data
        sequence.templates = self._personalize_templates(sequence.templates, lead_data)

        # Save sequence
        self._save_sequence(sequence)

        logger.info(f"Generated follow-up sequence for lead {sequence.lead_id}")
        return sequence

    def _personalize_templates(self, templates: List[FollowupTemplate], lead_data: Dict) -> List[FollowupTemplate]:
        """Personalize templates with lead-specific data."""
        personalized = []

        for template in templates:
            # Use AI to generate personalized content
            try:
                personalized_body = self._generate_personalized_body(template, lead_data)
                personalized_subject = self._generate_personalized_subject(template, lead_data)

                personalized_template = FollowupTemplate(
                    day=template.day,
                    name=template.name,
                    subject=personalized_subject,
                    body=personalized_body,
                    channel=template.channel,
                    purpose=template.purpose,
                    variables=template.variables
                )
                personalized.append(personalized_template)
            except Exception as e:
                logger.warning(f"Failed to personalize template {template.name}: {e}")
                personalized.append(template)

        return personalized

    def _generate_personalized_body(self, template: FollowupTemplate, lead_data: Dict) -> str:
        """Use AI to generate personalized email body."""
        prompt = f"""Generate a personalized follow-up email body based on this template and lead data.

TEMPLATE:
{template.body}

LEAD DATA:
- Company: {lead_data.get('company_name', 'N/A')}
- Industry: {lead_data.get('vertical', lead_data.get('primaryType', 'N/A'))}
- Contact: {lead_data.get('contact_name', lead_data.get('displayName', 'N/A'))}
- Pain Point: {lead_data.get('pain_point', 'looking for growth opportunities')}
- Previous Interaction: {lead_data.get('previous_interaction', 'none')}

Generate a natural, personalized email that:
1. References their specific situation
2. Sounds human (not templated)
3. Is concise (under 100 words)
4. Has a clear call-to-action

Return ONLY the email body, no explanations."""

        # Use generator service (would need to be implemented)
        # For now, return template with basic substitution
        body = template.body
        for var in template.variables:
            value = lead_data.get(var, lead_data.get(var.replace('_', ' '), f"[{var}]"))
            body = body.replace("{" + var + "}", str(value))
        return body

    def _generate_personalized_subject(self, template: FollowupTemplate, lead_data: Dict) -> str:
        """Generate personalized subject line."""
        subject = template.subject
        for var in template.variables:
            value = lead_data.get(var, lead_data.get(var.replace('_', ' '), f"[{var}]"))
            subject = subject.replace("{" + var + "}", str(value))
        return subject

    def get_next_followup(self, lead_id: str) -> Optional[FollowupTemplate]:
        """Get next follow-up template for a lead."""
        sequence = self._load_sequence(lead_id)
        if not sequence or sequence.status != "active":
            return None

        if sequence.completed_followups >= len(sequence.templates):
            return None

        return sequence.templates[sequence.completed_followups]

    def mark_completed(self, lead_id: str, sent: bool = True):
        """Mark current follow-up as completed."""
        sequence = self._load_sequence(lead_id)
        if not sequence:
            return

        sequence.completed_followups += 1

        if sent:
            # Schedule next follow-up
            if sequence.completed_followups < len(sequence.templates):
                next_template = sequence.templates[sequence.completed_followups]
                sequence.next_followup_at = (
                    datetime.now(timezone.utc) + timedelta(days=next_template.day)
                ).isoformat()
            else:
                sequence.status = "completed"
                sequence.next_followup_at = None

        self._save_sequence(sequence)

    def record_engagement(self, lead_id: str, event_type: str):
        """Record engagement and adjust sequence accordingly."""
        sequence = self._load_sequence(lead_id)
        if not sequence:
            return

        # Positive engagement accelerates sequence
        if event_type in ("opened", "clicked", "replied"):
            # Move next follow-up sooner
            if sequence.status == "active":
                next_date = datetime.fromisoformat(sequence.next_followup_at)
                # Reduce wait time by 50% for engaged leads
                new_date = next_date - timedelta(days=1)
                sequence.next_followup_at = max(datetime.now(timezone.utc), new_date).isoformat()
                logger.info(f"Accelerated follow-up for engaged lead {lead_id}")

        self._save_sequence(sequence)

    def _save_sequence(self, sequence: FollowupSequence):
        """Save sequence to file."""
        path = self.followups_dir / f"{sequence.lead_id}.json"
        with open(path, 'w') as f:
            json.dump(asdict(sequence), f, indent=2)

    def _load_sequence(self, lead_id: str) -> Optional[FollowupSequence]:
        """Load sequence from file."""
        path = self.followups_dir / f"{lead_id}.json"
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
            return FollowupSequence(**data)

    def get_due_followups(self) -> List[FollowupSequence]:
        """Get all sequences with follow-ups due now."""
        due = []
        now = datetime.now(timezone.utc)

        for path in self.followups_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    sequence = FollowupSequence(**data)

                    if sequence.status == "active":
                        next_date = datetime.fromisoformat(sequence.next_followup_at)
                        if next_date <= now:
                            due.append(sequence)
            except Exception as e:
                logger.error(f"Error loading sequence {path}: {e}")

        return due


def get_followup_service(config: Settings) -> FollowupService:
    """Get or create follow-up service."""
    return FollowupService(config)
