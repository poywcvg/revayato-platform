FROM node:22-bookworm-slim AS build

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NODE_ENV=development

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@11.12.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
# Cap the V8 heap so `nuxt build` GCs under the box's available RAM instead of
# ballooning toward the ~4GB default and getting OOM-killed (exit 137) on the
# 4-core prod host. Overridable at build time via --build-arg NODE_BUILD_MEM.
ARG NODE_BUILD_MEM=2560
ENV NODE_OPTIONS=--max-old-space-size=${NODE_BUILD_MEM}
RUN pnpm build

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production \
    NITRO_HOST=0.0.0.0 \
    NITRO_PORT=3000

WORKDIR /app

COPY --from=build --chown=node:node /app/.output ./.output

USER node

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]
