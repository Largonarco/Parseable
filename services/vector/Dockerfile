# Pinned to 0.37.0: Vector 0.38.0+ removed the json_array encoding codec.
# 0.37.0 is the last release that supports json_array, which is required
# to send batches as a JSON array [...] to Parseable's /api/v1/ingest endpoint.
FROM timberio/vector:0.37.0-alpine

COPY vector.toml /etc/vector/vector.toml

EXPOSE 9000 8686

CMD ["--config", "/etc/vector/vector.toml"]
