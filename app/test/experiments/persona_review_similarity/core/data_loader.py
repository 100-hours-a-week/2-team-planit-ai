"""
Data Loader for Experiment Datasets.

Updated to use production PoiData directly:
- Removed custom POIData class, uses app.core.models.PoiAgentDataclass.poi.PoiData
- ReviewData.pois is List[PoiData]
- JSON data must match PoiData schema (raw_text, source required)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.core.models.PersonaAgentDataclass.persona import QAItem
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiSource, PoiCategory


@dataclass
class ItineraryRequestData:
    """ItineraryRequest data matching app/schemas/persona.py"""
    tripId: int
    arrivalDate: str
    arrivalTime: str
    departureDate: str
    departureTime: str
    travelCity: str
    totalBudget: int
    travelTheme: List[str]
    wantedPlace: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItineraryRequestData":
        return cls(
            tripId=data.get("tripId", 0),
            arrivalDate=data.get("arrivalDate", ""),
            arrivalTime=data.get("arrivalTime", ""),
            departureDate=data.get("departureDate", ""),
            departureTime=data.get("departureTime", ""),
            travelCity=data.get("travelCity", ""),
            totalBudget=data.get("totalBudget", 0),
            travelTheme=data.get("travelTheme", []),
            wantedPlace=data.get("wantedPlace", []),
        )


@dataclass
class PersonaData:
    """Persona data matching TravelPersonaAgent structure."""

    id: str
    name: str
    itinerary_request: Optional[ItineraryRequestData]
    qa_items: List[QAItem]
    related_poi_ids: List[str]
    unrelated_poi_ids: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaData":
        # Parse itinerary_request if present
        itinerary_data = data.get("itinerary_request")
        itinerary_request = ItineraryRequestData.from_dict(itinerary_data) if itinerary_data else None

        # Parse QA items
        qa_items = [
            QAItem(
                id=qa.get("id", i),
                question=qa["question"],
                answer=qa.get("answer"),
            )
            for i, qa in enumerate(data.get("qa_items", []))
        ]

        return cls(
            id=data["id"],
            name=data["name"],
            itinerary_request=itinerary_request,
            qa_items=qa_items,
            related_poi_ids=data.get("related_poi_ids", []),
            unrelated_poi_ids=data.get("unrelated_poi_ids", []),
        )


def _parse_poi_from_dict(data: Dict[str, Any]) -> PoiData:
    """Parse a JSON dict into a production PoiData object."""
    # Map category string to PoiCategory enum
    category_str = data.get("category", "other")
    try:
        category = PoiCategory(category_str)
    except ValueError:
        category = PoiCategory.OTHER

    # Map source string to PoiSource enum
    source_str = data.get("source", "web_search")
    try:
        source = PoiSource(source_str)
    except ValueError:
        source = PoiSource.WEB_SEARCH

    return PoiData(
        id=data["id"],
        name=data["name"],
        category=category,
        description=data.get("description", ""),
        city=data.get("city"),
        address=data.get("address"),
        source=source,
        source_url=data.get("source_url"),
        raw_text=data.get("raw_text", data["name"]),
        google_place_id=data.get("google_place_id"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        google_maps_uri=data.get("google_maps_uri"),
        types=data.get("types", []),
        primary_type=data.get("primary_type"),
        google_rating=data.get("google_rating"),
        user_rating_count=data.get("user_rating_count"),
        price_level=data.get("price_level"),
        price_range=data.get("price_range"),
        website_uri=data.get("website_uri"),
        phone_number=data.get("phone_number"),
        editorial_summary=data.get("editorial_summary"),
        generative_summary=data.get("generative_summary"),
        review_summary=data.get("review_summary"),
    )


@dataclass
class ReviewData:
    """Collection of POI reviews using production PoiData."""

    version: str
    pois: List[PoiData]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewData":
        pois = [_parse_poi_from_dict(poi) for poi in data.get("pois", [])]
        return cls(version=data.get("version", "1.0"), pois=pois)

    def get_poi(self, poi_id: str) -> Optional[PoiData]:
        """Get POI by ID."""
        for poi in self.pois:
            if poi.id == poi_id:
                return poi
        return None


class DataLoader:
    """Load and validate experiment datasets."""

    def __init__(self, base_path: Optional[Union[str, Path]] = None):
        if base_path is None:
            base_path = Path(__file__).parent.parent / "data"
        self.base_path = Path(base_path)

    def load_personas(self, file_path: Union[str, Path]) -> List[PersonaData]:
        """Load persona dataset from JSON file."""
        path = self._resolve_path(file_path, "personas")
        data = self._load_json(path)
        self._validate_persona_schema(data)
        return [PersonaData.from_dict(p) for p in data.get("personas", [])]

    def load_reviews(self, file_path: Union[str, Path]) -> ReviewData:
        """Load review dataset from JSON file."""
        path = self._resolve_path(file_path, "reviews")
        data = self._load_json(path)
        self._validate_review_schema(data)
        return ReviewData.from_dict(data)

    def _resolve_path(self, file_path: Union[str, Path], subdir: str) -> Path:
        """Resolve file path, checking multiple locations."""
        path = Path(file_path)
        if path.is_absolute() and path.exists():
            return path
        # Check relative to base_path/subdir
        relative_path = self.base_path / subdir / path
        if relative_path.exists():
            return relative_path
        # Check relative to base_path directly
        direct_path = self.base_path / path
        if direct_path.exists():
            return direct_path
        raise FileNotFoundError(
            f"Dataset not found: {file_path}. "
            f"Checked: {path}, {relative_path}, {direct_path}"
        )

    def _load_json(self, path: Path) -> Dict[str, Any]:
        """Load JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _validate_persona_schema(self, data: Dict[str, Any]) -> None:
        """Validate persona dataset schema."""
        if "personas" not in data:
            raise ValueError("Persona dataset must have 'personas' key")
        for i, persona in enumerate(data["personas"]):
            required = ["id", "name", "qa_items"]
            for key in required:
                if key not in persona:
                    raise ValueError(
                        f"Persona {i} missing required key: {key}"
                    )

    def _validate_review_schema(self, data: Dict[str, Any]) -> None:
        """Validate review dataset schema."""
        if "pois" not in data:
            raise ValueError("Review dataset must have 'pois' key")
        for i, poi in enumerate(data["pois"]):
            required = ["id", "name", "raw_text", "source"]
            for key in required:
                if key not in poi:
                    raise ValueError(f"POI {i} missing required key: {key}")

    def list_persona_datasets(self) -> List[str]:
        """List available persona datasets."""
        personas_dir = self.base_path / "personas"
        if not personas_dir.exists():
            return []
        return [f.name for f in personas_dir.glob("*.json")]

    def list_review_datasets(self) -> List[str]:
        """List available review datasets."""
        reviews_dir = self.base_path / "reviews"
        if not reviews_dir.exists():
            return []
        return [f.name for f in reviews_dir.glob("*.json")]
