# ---- deps ----
FROM node:20-alpine AS deps
WORKDIR /repo/apps/web
# Copia ambos para que o cache da layer só quebre quando as deps mudarem.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --prefer-offline

# ---- builder ----
FROM node:20-alpine AS builder
WORKDIR /repo/apps/web
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /repo/apps/web/node_modules ./node_modules
COPY apps/web/ ./
# Type-only imports preserve the monorepo layout during Next's typecheck.
COPY packages/shared/src/ /repo/packages/shared/src/
RUN mkdir -p public
RUN npm run build

# ---- runner ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

COPY --from=builder /repo/apps/web/public ./public
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
