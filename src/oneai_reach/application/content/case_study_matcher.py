"""Case study matcher for proposals."""

import json
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass
import logging

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

@dataclass
class CaseStudy:
    id: str
    title: str
    industry: str
    company_size: str
    pain_point: str
    solution: str
    results: List[str]
    metrics: Dict[str, float]
    testimonial: str
    company_name: str
    content: str
    pdf_path: Optional[str] = None
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

class CaseStudyMatcher:
    def __init__(self, config: Settings):
        self.config = config
        self.case_studies_dir = Path(config.database.data_dir) / "case_studies"
        self.case_studies_dir.mkdir(parents=True, exist_ok=True)
        self._load_case_studies()

    def _load_case_studies(self):
        self.case_studies = []
        default_studies = [
            CaseStudy(id="cs_001", title="Digital Agency Increases Leads by 340%", industry="digital_agency", company_size="smb", pain_point="inconsistent lead flow", solution="Automated cold outreach", results=["340% more leads", "45% reply rate"], metrics={"lead_increase": 340}, testimonial="Transformed our pipeline", company_name="TechVision Agency", content="...", tags=["agency", "leads"]),
            CaseStudy(id="cs_002", title="Coffee Shop Chain Boosts Revenue 85%", industry="food_beverage", company_size="smb", pain_point="low retention", solution="B2B outreach", results=["85% revenue increase", "50+ clients"], metrics={"revenue_increase": 85}, testimonial="Game changer", company_name="Brew & Co", content="...", tags=["retail", "b2b"]),
        ]
        for path in self.case_studies_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    self.case_studies.append(CaseStudy(**json.load(f)))
            except: pass
        if not self.case_studies:
            self.case_studies = default_studies

    def match(self, lead_data: Dict, limit: int = 3) -> List[CaseStudy]:
        scores = [(s, self._score(s, lead_data)) for s in self.case_studies]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scores[:limit]]

    def _score(self, study: CaseStudy, lead: Dict) -> float:
        score = 0.0
        lead_ind = lead.get("vertical", lead.get("primaryType", "")).lower()
        if study.industry in lead_ind or lead_ind in study.industry: score += 50
        if study.company_size == self._size(lead): score += 20
        if study.pain_point.lower() in str(lead.get("pain_points", "")).lower(): score += 30
        return score

    def _size(self, lead: Dict) -> str:
        emp = lead.get("employees", 0)
        try: emp = int(emp)
        except: emp = 0
        return "startup" if emp < 10 else "smb" if emp < 100 else "enterprise"

def get_case_study_matcher(config: Settings) -> CaseStudyMatcher:
    return CaseStudyMatcher(config)
