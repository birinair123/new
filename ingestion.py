"""Ingestion service for processing data files."""

import csv
import json
import os
from datetime import datetime
from typing import Optional
import pandas as pd

from models import Database, DataRecord, IngestionJob, IngestionStatus


class IngestionService:
    """Service for ingesting data from various file formats."""

    SUPPORTED_FORMATS = [".csv", ".json", ".xlsx", ".xls"]

    def __init__(self, db: Database):
        self.db = db

    def ingest_file(self, filepath: str, source_name: Optional[str] = None) -> IngestionJob:
        """
        Ingest data from a file into the database.

        Args:
            filepath: Path to the file to ingest
            source_name: Optional name for the data source

        Returns:
            IngestionJob with the results
        """
        session = self.db.get_session()
        filename = os.path.basename(filepath)
        source = source_name or filename

        job = IngestionJob(
            filename=filename,
            status=IngestionStatus.PROCESSING.value
        )
        session.add(job)
        session.commit()

        try:
            ext = os.path.splitext(filepath)[1].lower()

            if ext == ".csv":
                records = self._parse_csv(filepath)
            elif ext == ".json":
                records = self._parse_json(filepath)
            elif ext in [".xlsx", ".xls"]:
                records = self._parse_excel(filepath)
            else:
                raise ValueError(f"Unsupported file format: {ext}")

            processed = 0
            failed = 0

            for record_data in records:
                try:
                    record = DataRecord(
                        source=source,
                        name=str(record_data.get("name", "Unknown")),
                        value=self._parse_float(record_data.get("value")),
                        category=record_data.get("category"),
                        description=record_data.get("description"),
                    )
                    session.add(record)
                    processed += 1
                except Exception:
                    failed += 1

            session.commit()

            job.status = IngestionStatus.COMPLETED.value
            job.records_processed = processed
            job.records_failed = failed
            job.completed_at = datetime.utcnow()
            session.commit()

        except Exception as e:
            job.status = IngestionStatus.FAILED.value
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            session.commit()

        session.refresh(job)
        session.close()
        return job

    def ingest_records(self, records: list[dict], source_name: str) -> IngestionJob:
        """
        Ingest data records directly into the database.

        Args:
            records: List of record dictionaries
            source_name: Name for the data source

        Returns:
            IngestionJob with the results
        """
        session = self.db.get_session()

        job = IngestionJob(
            filename=f"direct_input:{source_name}",
            status=IngestionStatus.PROCESSING.value
        )
        session.add(job)
        session.commit()

        processed = 0
        failed = 0

        try:
            for record_data in records:
                try:
                    record = DataRecord(
                        source=source_name,
                        name=str(record_data.get("name", "Unknown")),
                        value=self._parse_float(record_data.get("value")),
                        category=record_data.get("category"),
                        description=record_data.get("description"),
                    )
                    session.add(record)
                    processed += 1
                except Exception:
                    failed += 1

            session.commit()

            job.status = IngestionStatus.COMPLETED.value
            job.records_processed = processed
            job.records_failed = failed
            job.completed_at = datetime.utcnow()
            session.commit()

        except Exception as e:
            job.status = IngestionStatus.FAILED.value
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            session.commit()

        session.refresh(job)
        session.close()
        return job

    def _parse_csv(self, filepath: str) -> list[dict]:
        """Parse CSV file and return list of record dictionaries."""
        records = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(dict(row))
        return records

    def _parse_json(self, filepath: str) -> list[dict]:
        """Parse JSON file and return list of record dictionaries."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                if "records" in data:
                    return data["records"]
                elif "data" in data:
                    return data["data"]
                return [data]
        return []

    def _parse_excel(self, filepath: str) -> list[dict]:
        """Parse Excel file and return list of record dictionaries."""
        df = pd.read_excel(filepath)
        return df.to_dict(orient="records")

    def _parse_float(self, value) -> Optional[float]:
        """Safely parse a value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_all_records(self, limit: int = 100, offset: int = 0) -> list[DataRecord]:
        """Get all data records with pagination."""
        session = self.db.get_session()
        records = session.query(DataRecord).order_by(
            DataRecord.created_at.desc()
        ).offset(offset).limit(limit).all()
        session.close()
        return records

    def get_records_by_source(self, source: str) -> list[DataRecord]:
        """Get all records from a specific source."""
        session = self.db.get_session()
        records = session.query(DataRecord).filter(
            DataRecord.source == source
        ).order_by(DataRecord.created_at.desc()).all()
        session.close()
        return records

    def get_records_by_category(self, category: str) -> list[DataRecord]:
        """Get all records in a specific category."""
        session = self.db.get_session()
        records = session.query(DataRecord).filter(
            DataRecord.category == category
        ).order_by(DataRecord.created_at.desc()).all()
        session.close()
        return records

    def search_records(self, query: str) -> list[DataRecord]:
        """Search records by name or description."""
        session = self.db.get_session()
        search_pattern = f"%{query}%"
        records = session.query(DataRecord).filter(
            (DataRecord.name.like(search_pattern)) |
            (DataRecord.description.like(search_pattern))
        ).order_by(DataRecord.created_at.desc()).all()
        session.close()
        return records

    def get_all_jobs(self, limit: int = 50) -> list[IngestionJob]:
        """Get all ingestion jobs."""
        session = self.db.get_session()
        jobs = session.query(IngestionJob).order_by(
            IngestionJob.started_at.desc()
        ).limit(limit).all()
        session.close()
        return jobs

    def get_statistics(self) -> dict:
        """Get statistics about ingested data."""
        session = self.db.get_session()

        total_records = session.query(DataRecord).count()
        total_jobs = session.query(IngestionJob).count()

        sources = session.query(DataRecord.source).distinct().all()
        categories = session.query(DataRecord.category).distinct().all()

        completed_jobs = session.query(IngestionJob).filter(
            IngestionJob.status == IngestionStatus.COMPLETED.value
        ).count()

        failed_jobs = session.query(IngestionJob).filter(
            IngestionJob.status == IngestionStatus.FAILED.value
        ).count()

        session.close()

        return {
            "total_records": total_records,
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "unique_sources": len(sources),
            "unique_categories": len([c for c in categories if c[0] is not None]),
        }

    def delete_record(self, record_id: int) -> bool:
        """Delete a record by ID."""
        session = self.db.get_session()
        record = session.query(DataRecord).filter(DataRecord.id == record_id).first()
        if record:
            session.delete(record)
            session.commit()
            session.close()
            return True
        session.close()
        return False
