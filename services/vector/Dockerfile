FROM timberio/vector:0.43.0-alpine

COPY vector.toml /etc/vector/vector.toml

EXPOSE 9000 8686

CMD ["--config", "/etc/vector/vector.toml"]
