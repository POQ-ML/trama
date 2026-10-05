# ADR 001 — Arquitetura inicial

Data: 2026-10-05
Status: aceita

## Contexto
Precisamos de base executável e simples para o MVP.

## Decisão
Monorepo com Next.js + FastAPI + PostgreSQL via Docker Compose.
Domínio, conectores e IA apenas como abstrações.

## Consequências
Setup em um comando. Crescimento sem reescrita da fundação.
Sem overengineering (sem K8s, filas ou microserviços).
