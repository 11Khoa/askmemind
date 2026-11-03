"""Demo request dependencies, defined alongside auth to avoid import cycles."""
from app.core.dependencies import get_data_scope, require_demo_notice, require_demo_upload
