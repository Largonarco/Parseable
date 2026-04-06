# Vector log aggregator for the Parseable Observability Stack.
# Receives JSON log batches from apps and forwards them to Parseable.
FROM timberio/vector:0.38.0-alpine

COPY vector.toml /etc/vector/vector.toml

EXPOSE 9000 8686

CMD ["--config", "/etc/vector/vector.toml"]
