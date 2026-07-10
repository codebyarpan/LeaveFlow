# The `web` service: build the React bundle, then serve it statically (AC1, AC4, AC8).

# --- build stage -------------------------------------------------------------
# node:24-alpine satisfies Vite 8's engines requirement of ^20.19.0 || >=22.12.0.
FROM node:24-alpine AS build

WORKDIR /build

# `npm ci` installs from the lockfile exactly, which is what AC7's "every version matches
# exactly" means for the frontend. `npm install` would be free to resolve something else.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig*.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src

# `tsc -b && vite build`. A type error fails the image build rather than shipping.
RUN npm run build

# --- serve stage -------------------------------------------------------------
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
