# Stage 1: Build the application
FROM maven:3.8.4-openjdk-17-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/dsainatarajan/springemployeecrud .
RUN mvn clean package

# Stage 2: Create the final image
FROM openjdk:11-ea-17-jre-slim
WORKDIR /app
COPY --from=build /app/target/springdatademo-0.0.1-SNAPSHOT.jar .
EXPOSE 8181
CMD ["java", "-jar", "springdatademo-0.0.1-SNAPSHOT.jar"]