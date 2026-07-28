# frontend/Dockerfile
FROM node:20-slim

WORKDIR /app

# Install dependencies BEFORE copying code -> leverage Docker layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]