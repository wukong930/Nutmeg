FROM node:24-slim AS deps

WORKDIR /app/apps/web
ENV NEXT_TELEMETRY_DISABLED=1

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder

WORKDIR /app/apps/web
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/apps/web/node_modules ./node_modules
COPY apps/web ./
RUN npm run build
RUN npm prune --omit=dev

FROM node:24-slim AS runner

WORKDIR /app/apps/web
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/apps/web/package.json ./package.json
COPY --from=builder /app/apps/web/node_modules ./node_modules
COPY --from=builder /app/apps/web/.next ./.next
COPY --from=builder /app/apps/web/public ./public

EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
