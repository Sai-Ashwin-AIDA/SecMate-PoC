"""Local tool-attempt evidence accounting, independent of enforcement budgets."""

ACCOUNTING_VERSION = "tool-request-accounting-v1"
_FLAGS = ("reservation_requested", "reservation_accepted", "http_dispatched", "response_received")


def lifecycle(event, *, required=False):
    value = event.get("request_accounting")
    if value is None:
        if required:
            raise ValueError("provider_lifecycle_missing")
        # Old exports have no lifecycle flags. Preserve their reader shape while
        # excluding the identifiable reservation rejection seen in retained s3.
        rejected = (event.get("error_code") == "BUDGET_EXHAUSTED"
                    and event.get("estimated_tokens") is None
                    and event.get("usage") is None
                    and event.get("status_code") is None
                    and event.get("provider_request_id") is None)
        return {"reservation_requested": True, "reservation_accepted": not rejected,
                "http_dispatched": not rejected,
                "response_received": event.get("status_code") is not None or event.get("outcome") == "SUCCESS"}
    if (not isinstance(value, dict) or set(value) != {"schema_version", *_FLAGS}
            or value["schema_version"] != ACCOUNTING_VERSION
            or any(type(value[key]) is not bool for key in _FLAGS)):
        raise ValueError("provider_lifecycle_shape")
    if (not value["reservation_requested"]
            or value["http_dispatched"] and not value["reservation_accepted"]
            or value["response_received"] and not value["http_dispatched"]
            or event.get("outcome") == "SUCCESS" and not value["response_received"]):
        raise ValueError("provider_lifecycle_order")
    return value


def summarize(events, *, required=False):
    states = [lifecycle(event, required=required) for event in events]
    return {
        "reservation_requests": sum(item["reservation_requested"] for item in states),
        "reservations_accepted": sum(item["reservation_accepted"] for item in states),
        "preflight_rejections": sum(not item["reservation_accepted"] for item in states),
        "http_dispatches": sum(item["http_dispatched"] for item in states),
        "responses_received": sum(item["response_received"] for item in states),
    }
