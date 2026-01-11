import enum

import prometheus_client


class Metrics(enum.Enum):
    # cleezy moment
    LAST_SMEE_REQUEST = (
        "last_smee_request_timestamp",
        "last request from Smee",
        prometheus_client.Gauge,
    )
    LAST_PUSH_TIMESTAMP = (
        "last_push_timestamp",
        "last Git push",
        prometheus_client.Gauge,
        ["repo"],
    )
    DOCKER_IMAGE_DISK_USAGE_BYTES = (
        "docker_image_disk_usage_bytes",
        "Total disk usage of all Docker images in bytes",
        prometheus_client.Gauge,
    )

    def __init__(self, title, description, prometheus_type, labels=()):
        # we use the above default value for labels because it matches what's used
        # in the prometheus_client library's metrics constructor, see
        # https://github.com/prometheus/client_python/blob/fd4da6cde36a1c278070cf18b4b9f72956774b05/prometheus_client/metrics.py#L115
        self.title = title
        self.description = description
        self.prometheus_type = prometheus_type
        self.labels = labels


class MetricsHandler:
    @classmethod
    def init(cls) -> None:
        for metric in Metrics:
            setattr(
                cls,
                metric.title,
                metric.prometheus_type(
                    metric.title, metric.description, labelnames=metric.labels
                ),
            )
