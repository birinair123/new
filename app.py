"""Flask web application for data ingestion system."""

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from models import Database
from ingestion import IngestionService

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = Database()
ingestion_service = IngestionService(db)


@app.route("/")
def index():
    """Dashboard home page."""
    stats = ingestion_service.get_statistics()
    recent_records = ingestion_service.get_all_records(limit=10)
    recent_jobs = ingestion_service.get_all_jobs(limit=5)
    return render_template(
        "index.html",
        stats=stats,
        recent_records=recent_records,
        recent_jobs=recent_jobs
    )


@app.route("/records")
def records():
    """View all data records."""
    page = request.args.get("page", 1, type=int)
    per_page = 25
    offset = (page - 1) * per_page

    search = request.args.get("search", "")
    source = request.args.get("source", "")
    category = request.args.get("category", "")

    if search:
        all_records = ingestion_service.search_records(search)
    elif source:
        all_records = ingestion_service.get_records_by_source(source)
    elif category:
        all_records = ingestion_service.get_records_by_category(category)
    else:
        all_records = ingestion_service.get_all_records(limit=500)

    total = len(all_records)
    records_page = all_records[offset:offset + per_page]
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "records.html",
        records=records_page,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        source=source,
        category=category
    )


@app.route("/ingest", methods=["GET", "POST"])
def ingest():
    """File upload and ingestion page."""
    if request.method == "POST":
        if "file" in request.files:
            file = request.files["file"]
            if file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)

                source_name = request.form.get("source_name") or filename
                job = ingestion_service.ingest_file(filepath, source_name)

                if job.status == "completed":
                    flash(
                        f"Successfully ingested {job.records_processed} records from {filename}",
                        "success"
                    )
                else:
                    flash(f"Ingestion failed: {job.error_message}", "error")

                return redirect(url_for("jobs"))

        flash("No file selected", "error")
        return redirect(url_for("ingest"))

    return render_template("ingest.html")


@app.route("/ingest/manual", methods=["POST"])
def ingest_manual():
    """Manual data entry ingestion."""
    source_name = request.form.get("source_name", "Manual Entry")
    name = request.form.get("name")
    value = request.form.get("value")
    category = request.form.get("category")
    description = request.form.get("description")

    if not name:
        flash("Name is required", "error")
        return redirect(url_for("ingest"))

    records = [{
        "name": name,
        "value": value,
        "category": category,
        "description": description
    }]

    job = ingestion_service.ingest_records(records, source_name)

    if job.status == "completed":
        flash("Record added successfully", "success")
    else:
        flash(f"Failed to add record: {job.error_message}", "error")

    return redirect(url_for("records"))


@app.route("/jobs")
def jobs():
    """View ingestion job history."""
    all_jobs = ingestion_service.get_all_jobs(limit=100)
    return render_template("jobs.html", jobs=all_jobs)


@app.route("/records/<int:record_id>/delete", methods=["POST"])
def delete_record(record_id):
    """Delete a record."""
    if ingestion_service.delete_record(record_id):
        flash("Record deleted successfully", "success")
    else:
        flash("Record not found", "error")
    return redirect(url_for("records"))


@app.route("/api/records")
def api_records():
    """API endpoint to get records as JSON."""
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    records = ingestion_service.get_all_records(limit=limit, offset=offset)
    return jsonify([r.to_dict() for r in records])


@app.route("/api/stats")
def api_stats():
    """API endpoint to get statistics."""
    stats = ingestion_service.get_statistics()
    return jsonify(stats)


@app.route("/api/jobs")
def api_jobs():
    """API endpoint to get jobs as JSON."""
    jobs = ingestion_service.get_all_jobs()
    return jsonify([j.to_dict() for j in jobs])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
