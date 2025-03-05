ARG SNAPCAST_VERSION=0.0.2

# Use Node.js base image
FROM node:alpine

# Set working directory
WORKDIR /app

# Copy files
COPY package*.json ./
COPY traffic-grabber.js ./

# Install dependencies
RUN npm install express prom-client

# Expose metrics port
EXPOSE 9100

# Start the application
CMD ["node", "traffic-grabber.js"]