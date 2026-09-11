"""Spring Boot (Java 17) generator."""

from __future__ import annotations

from typing import Any

from app.services.codegen.base import (
    JAVA_IMPORT_MAP,
    JAVA_TYPE_MAP,
    blueprint_context,
    camel_case,
    column_precision,
    is_nullable,
    is_pk,
    is_unique,
    map_type,
    pascal_case,
    render_template,
    singularize,
    snake_case,
    table_columns,
    table_plural,
)

SPRING_README = """# __PROJECT_NAME__ - Spring Boot API

Spring Boot 3 REST API generated from the project blueprint. Layered
architecture: `controller` -> `service` -> `repository` -> `entity`.

## Features

- JWT authentication (register / login / me) with a stateless security filter
- CRUD API for `__TABLE__` with Bean Validation (jakarta.validation)
- Centralized exception handling (`@RestControllerAdvice`)
- Springdoc OpenAPI docs at http://localhost:8080/swagger-ui.html
- Tests with Spring Boot Test, Docker + docker-compose

## Quick start

```bash
docker compose up --build          # API + PostgreSQL
# or locally:
mvn spring-boot:run                # requires Java 17+ and PostgreSQL
```

Swagger UI: http://localhost:8080/swagger-ui.html

## Test

```bash
mvn test
```

## Structure

```text
src/main/java/__PACKAGE_PATH__/
  config/         security config, JWT filter, OpenAPI
  auth/           register/login endpoints, DTOs
  user/           User entity + repository
  __MODEL_LOWER__/  __MODEL__ entity, repository, service, controller, DTOs
  common/         ApiException + global handler
  __APP_CLASS__Application.java
```

> Replace `app.jwt-secret` in `application.yml` before deploying.
"""

SPRING_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>__GROUP_ID__</groupId>
    <artifactId>__APP_SLUG__-api</artifactId>
    <version>0.1.0</version>
    <name>__APP_SLUG__-api</name>
    <description>__PROJECT_NAME__ REST API generated from an AI blueprint</description>

    <properties>
        <java.version>17</java.version>
        <springdoc.version>2.6.0</springdoc.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>${springdoc.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""

SPRING_APPLICATION_YML = """spring:
  application:
    name: __APP_SLUG__-api
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/__APP_SLUG__}
    username: ${DB_USER:app}
    password: ${DB_PASSWORD:app_password}
  jpa:
    hibernate:
      ddl-auto: update
    open-in-view: false
    properties:
      hibernate:
        format_sql: true

server:
  port: ${PORT:8080}

app:
  jwt:
    secret: ${JWT_SECRET:CHANGE_ME_secret_key_at_least_32_chars}
    expiration-ms: ${JWT_EXPIRATION_MS:86400000}

springdoc:
  swagger-ui:
    path: /swagger-ui.html
"""

SPRING_ENV_EXAMPLE = """# Database
DB_URL=jdbc:postgresql://localhost:5432/__APP_SLUG__
DB_USER=app
DB_PASSWORD=app_password

# Auth
JWT_SECRET=CHANGE_ME_secret_key_at_least_32_chars
JWT_EXPIRATION_MS=86400000
"""

SPRING_DOCKERFILE = """FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
"""

SPRING_COMPOSE = """services:
  api:
    build: .
    container_name: __APP_SLUG___api
    ports:
      - "8080:8080"
    environment:
      DB_URL: jdbc:postgresql://db:5432/__APP_SLUG__
      DB_USER: app
      DB_PASSWORD: app_password
      JWT_SECRET: CHANGE_ME_secret_key_at_least_32_chars
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    container_name: __APP_SLUG___db
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app_password
      POSTGRES_DB: __APP_SLUG__
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d __APP_SLUG__"]
      interval: 5s
      timeout: 5s
      retries: 5
"""

SPRING_GITIGNORE = """target/
.idea/
*.iml
.vscode/
.env
"""

SPRING_APPLICATION = """package __PACKAGE__;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class __APP_CLASS__Application {

    public static void main(String[] args) {
        SpringApplication.run(__APP_CLASS__Application.class, args);
    }
}
"""

SPRING_API_EXCEPTION = """package __PACKAGE__.common;

public class ApiException extends RuntimeException {

    private final int status;

    public ApiException(int status, String message) {
        super(message);
        this.status = status;
    }

    public int getStatus() {
        return status;
    }
}
"""

SPRING_EXCEPTION_HANDLER = """package __PACKAGE__.common;

import java.util.HashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> handleApi(ApiException ex) {
        Map<String, Object> body = new HashMap<>();
        body.put("success", false);
        body.put("message", ex.getMessage());
        return ResponseEntity.status(ex.getStatus()).body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException ex) {
        Map<String, Object> body = new HashMap<>();
        Map<String, String> errors = new HashMap<>();
        ex.getBindingResult().getFieldErrors().forEach(e -> errors.put(e.getField(), e.getDefaultMessage()));
        body.put("success", false);
        body.put("message", "Validation failed");
        body.put("details", errors);
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleGeneric(Exception ex) {
        Map<String, Object> body = new HashMap<>();
        body.put("success", false);
        body.put("message", "Internal server error");
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
    }
}
"""

SPRING_JWT_SERVICE = """package __PACKAGE__.config;

import java.nio.charset.StandardCharsets;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class JwtService {

    private static final String HMAC_ALGO = "HmacSHA256";

    private final byte[] secret;

    private final long expirationMs;

    public JwtService(
            @Value("${app.jwt.secret}") String secret,
            @Value("${app.jwt.expiration-ms}") long expirationMs) {
        this.secret = secret.getBytes(StandardCharsets.UTF_8);
        this.expirationMs = expirationMs;
    }

    public String generateToken(Long userId) {
        long issuedAt = System.currentTimeMillis();
        String header = base64("{\\"alg\\":\\"HS256\\",\\"typ\\":\\"JWT\\"}");
        String payload = base64("{\\"sub\\":\\"" + userId + "\\",\\"iat\\":"
                + issuedAt + ",\\"exp\\":" + (issuedAt + expirationMs) + "}");
        String signingInput = header + "." + payload;
        return signingInput + "." + base64(hmac(signingInput));
    }

    public Long parseUserId(String token) {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            throw new IllegalArgumentException("Malformed JWT");
        }
        String signingInput = parts[0] + "." + parts[1];
        if (!base64(hmac(signingInput)).equals(parts[2])) {
            throw new IllegalArgumentException("Invalid JWT signature");
        }
        String payload = new String(java.util.Base64.getUrlDecoder().decode(parts[1]));
        String sub = payload.replaceAll(".*\\"sub\\":\\"([^\\"]*).*", "$1");
        return Long.parseLong(sub);
    }

    private String hmac(String input) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGO);
            mac.init(new SecretKeySpec(secret, HMAC_ALGO));
            return new String(mac.doFinal(input.getBytes(StandardCharsets.UTF_8)), StandardCharsets.ISO_8859_1);
        } catch (Exception e) {
            throw new IllegalStateException("HMAC failure", e);
        }
    }

    private static String base64(String value) {
        return java.util.Base64.getUrlEncoder().withoutPadding()
                .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }
}
"""

SPRING_SECURITY_FILTER = """package __PACKAGE__.config;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import __PACKAGE__.user.User;
import __PACKAGE__.user.UserRepository;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtService jwtService;

    private final UserRepository userRepository;

    public JwtAuthenticationFilter(JwtService jwtService, UserRepository userRepository) {
        this.jwtService = jwtService;
        this.userRepository = userRepository;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            try {
                Long userId = jwtService.parseUserId(header.substring(7));
                userRepository.findById(userId).ifPresent(user -> {
                    var authorities = List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole().toUpperCase()));
                    var authentication = new UsernamePasswordAuthenticationToken(user, null, authorities);
                    SecurityContextHolder.getContext().setAuthentication(authentication);
                });
            } catch (IllegalArgumentException ignored) {
                // invalid token -> anonymous, secured endpoints will reject
            }
        }
        filterChain.doFilter(request, response);
    }
}
"""

SPRING_SECURITY_CONFIG = """package __PACKAGE__.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/v1/auth/**", "/health").permitAll()
                        .requestMatchers("/swagger-ui/**", "/swagger-ui.html", "/v3/api-docs/**").permitAll()
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .anyRequest().authenticated())
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
"""

SPRING_OPENAPI_CONFIG = """package __PACKAGE__.config;

import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@OpenAPIDefinition(info = @Info(title = "__PROJECT_NAME__ API", version = "0.1.0",
        description = "REST API generated from an AI blueprint."))
@SecurityScheme(name = "bearerAuth", type = SecuritySchemeType.HTTP, scheme = "bearer", bearerFormat = "JWT")
public class OpenApiConfig {
}
"""

SPRING_HEALTH = """package __PACKAGE__;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class HealthController {

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "service", "__APP_SLUG__");
    }
}
"""

SPRING_USER_ENTITY = """package __PACKAGE__.user;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Column(name = "full_name", length = 150)
    private String fullName;

    @Column(nullable = false, length = 50)
    private String role = "user";

    @Column(name = "is_active", nullable = false)
    private boolean isActive = true;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public void setPasswordHash(String passwordHash) {
        this.passwordHash = passwordHash;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public boolean isActive() {
        return isActive;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
"""

SPRING_USER_REPOSITORY = """package __PACKAGE__.user;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByEmail(String email);

    boolean existsByEmail(String email);
}
"""

SPRING_AUTH_DTOS = """package __PACKAGE__.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegisterRequest {

    @Email
    @NotBlank
    private String email;

    @NotBlank
    @Size(min = 8, message = "Password must be at least 8 characters")
    private String password;

    @Size(max = 150)
    private String fullName;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
"""

SPRING_AUTH_LOGIN = """package __PACKAGE__.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class LoginRequest {

    @Email
    @NotBlank
    private String email;

    @NotBlank
    private String password;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
"""

SPRING_AUTH_RESPONSE = """package __PACKAGE__.auth.dto;

public record AuthResponse(String accessToken, String tokenType, UserDto user) {

    public record UserDto(Long id, String email, String fullName, String role) {
    }
}
"""

SPRING_AUTH_SERVICE = """package __PACKAGE__.auth;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import __PACKAGE__.auth.dto.AuthResponse;
import __PACKAGE__.auth.dto.LoginRequest;
import __PACKAGE__.auth.dto.RegisterRequest;
import __PACKAGE__.common.ApiException;
import __PACKAGE__.config.JwtService;
import __PACKAGE__.user.User;
import __PACKAGE__.user.UserRepository;

@Service
public class AuthService {

    private final UserRepository userRepository;

    private final PasswordEncoder passwordEncoder;

    private final JwtService jwtService;

    public AuthService(UserRepository userRepository, PasswordEncoder passwordEncoder,
            JwtService jwtService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
    }

    @Transactional
    public AuthResponse register(RegisterRequest request) {
        if (userRepository.existsByEmail(request.getEmail().toLowerCase())) {
            throw new ApiException(409, "Email already registered");
        }
        User user = new User();
        user.setEmail(request.getEmail().toLowerCase());
        user.setPasswordHash(passwordEncoder.encode(request.getPassword()));
        user.setFullName(request.getFullName());
        User saved = userRepository.save(user);
        return toResponse(saved);
    }

    public AuthResponse login(LoginRequest request) {
        User user = userRepository.findByEmail(request.getEmail().toLowerCase())
                .filter(User::isActive)
                .orElseThrow(() -> new ApiException(401, "Invalid email or password"));
        if (!passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
            throw new ApiException(401, "Invalid email or password");
        }
        return toResponse(user);
    }

    private AuthResponse toResponse(User user) {
        AuthResponse.UserDto dto = new AuthResponse.UserDto(
                user.getId(), user.getEmail(), user.getFullName(), user.getRole());
        return new AuthResponse(jwtService.generateToken(user.getId()), "bearer", dto);
    }
}
"""

SPRING_AUTH_CONTROLLER = """package __PACKAGE__.auth;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.security.SecurityRequirement;

import __PACKAGE__.auth.dto.AuthResponse;
import __PACKAGE__.auth.dto.LoginRequest;
import __PACKAGE__.auth.dto.RegisterRequest;
import __PACKAGE__.user.User;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public AuthResponse register(@Valid @RequestBody RegisterRequest request) {
        return authService.register(request);
    }

    @PostMapping("/login")
    public AuthResponse login(@Valid @RequestBody LoginRequest request) {
        return authService.login(request);
    }

    @GetMapping("/me")
    @SecurityRequirement(name = "bearerAuth")
    public AuthResponse.UserDto me(org.springframework.security.core.Authentication authentication) {
        User user = (User) authentication.getPrincipal();
        return new AuthResponse.UserDto(
                user.getId(), user.getEmail(), user.getFullName(), user.getRole());
    }
}
"""

SPRING_ENTITY_TEMPLATE = """package __PACKAGE__.__MODEL_LOWER__;

__IMPORTS__
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "__TABLE__")
public class __MODEL__ {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

__FIELDS__
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }
__GETTERS_SETTERS__}
"""

SPRING_REPOSITORY_TEMPLATE = """package __PACKAGE__.__MODEL_LOWER__;

import org.springframework.data.jpa.repository.JpaRepository;

public interface __MODEL__Repository extends JpaRepository<__MODEL__, Long> {
}
"""

SPRING_REQUEST_TEMPLATE = """package __PACKAGE__.__MODEL_LOWER__.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class __MODEL__Request {

__FIELDS__
}
"""

SPRING_RESPONSE_TEMPLATE = """package __PACKAGE__.__MODEL_LOWER__.dto;

public record __MODEL__Response(
__FIELDS__) {
}
"""

SPRING_SERVICE_TEMPLATE = """package __PACKAGE__.__MODEL_LOWER__;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import __PACKAGE__.__MODEL_LOWER__.dto.__MODEL__Request;
import __PACKAGE__.__MODEL_LOWER__.dto.__MODEL__Response;
import __PACKAGE__.common.ApiException;

@Service
public class __MODEL__Service {

    private final __MODEL__Repository repository;

    public __MODEL__Service(__MODEL__Repository repository) {
        this.repository = repository;
    }

    public List<__MODEL__Response> findAll() {
        return repository.findAll().stream().map(this::toResponse).toList();
    }

    public __MODEL__Response findById(Long id) {
        return toResponse(getEntity(id));
    }

    @Transactional
    public __MODEL__Response create(__MODEL__Request request) {
        __MODEL__ entity = new __MODEL__();
        apply(entity, request);
        return toResponse(repository.save(entity));
    }

    @Transactional
    public __MODEL__Response update(Long id, __MODEL__Request request) {
        __MODEL__ entity = getEntity(id);
        apply(entity, request);
        return toResponse(repository.save(entity));
    }

    @Transactional
    public void delete(Long id) {
        repository.delete(getEntity(id));
    }

    private __MODEL__ getEntity(Long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ApiException(404, "__MODEL__ not found"));
    }

    private void apply(__MODEL__ entity, __MODEL__Request request) {
__APPLY__
    }

    private __MODEL__Response toResponse(__MODEL__ entity) {
        return new __MODEL__Response(
__TO_RESPONSE__);
    }
}
"""

SPRING_CONTROLLER_TEMPLATE = """package __PACKAGE__.__MODEL_LOWER__;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.security.SecurityRequirement;

import __PACKAGE__.__MODEL_LOWER__.dto.__MODEL__Request;
import __PACKAGE__.__MODEL_LOWER__.dto.__MODEL__Response;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/v1/__PLURAL_LOWER__")
@SecurityRequirement(name = "bearerAuth")
public class __MODEL__Controller {

    private final __MODEL__Service service;

    public __MODEL__Controller(__MODEL__Service service) {
        this.service = service;
    }

    @GetMapping
    public List<__MODEL__Response> findAll() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public __MODEL__Response findById(@PathVariable Long id) {
        return service.findById(id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public __MODEL__Response create(@Valid @RequestBody __MODEL__Request request) {
        return service.create(request);
    }

    @PatchMapping("/{id}")
    public __MODEL__Response update(@PathVariable Long id, @Valid @RequestBody __MODEL__Request request) {
        return service.update(id, request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        service.delete(id);
    }
}
"""

SPRING_APPLICATION_TESTS = """package __PACKAGE__;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class __APP_CLASS__ApplicationTests {

    @Test
    void contextLoads() {
    }
}
"""

SPRING_TEST_PROPS = """spring.datasource.url=jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
"""


def _java_type(column: dict[str, Any]) -> str:
    return map_type(column.get("type") or "TEXT", JAVA_TYPE_MAP)


def _java_imports(types: set[str]) -> str:
    imports: set[str] = set()
    for t in types:
        imports |= JAVA_IMPORT_MAP.get(t, set())
    return "\n".join(f"import {imp};" for imp in sorted(imports))


def _spring_tokens(context: dict[str, Any]) -> dict[str, str]:
    primary = context["primary_table"]
    table_name = primary.get("name") or "items"
    model = pascal_case(singularize(table_name))
    package = context["app_package"]
    group_id = ".".join(package.split(".")[:2]) or "com.example.app"
    return {
        "PROJECT_NAME": context["project_name"],
        "APP_SLUG": context["app_slug"],
        "APP_CLASS": context["app_class"],
        "PACKAGE": package,
        "PACKAGE_PATH": package.replace(".", "/"),
        "GROUP_ID": group_id,
        "MODEL": model,
        "MODEL_LOWER": snake_case(singularize(table_name)),
        "PLURAL_LOWER": table_plural(table_name).lower(),
        "TABLE": table_name,
    }


def _java_entity(table: dict[str, Any], tokens: dict[str, str]) -> str:
    types: set[str] = set()
    fields: list[str] = []

    for column in table_columns(table):
        name = column.get("name") or ""
        java_type = _java_type(column)
        types.add(java_type)
        precision = column_precision(column.get("type") or "")
        nullable = is_nullable(column)
        unique = is_unique(column)
        attrs = [f'name = "{name}"']
        if not nullable and name != "id":
            attrs.append("nullable = false")
        if unique:
            attrs.append("unique = true")
        if precision and java_type == "String":
            attrs.append(f"length = {precision}")
        field_name = camel_case(name)
        if name != "id":
            fields.append(
                f"    @Column({', '.join(attrs)})\n"
                f"    private {java_type} {field_name};\n"
            )

    getters_setters: list[str] = []
    for column in table_columns(table):
        name = column.get("name") or ""
        if name == "id":
            continue
        java_type = _java_type(column)
        field_name = camel_case(name)
        accessor = "is" if java_type == "Boolean" and not field_name.startswith("is") else "get"
        getter = f"is{field_name[:1].upper()}{field_name[1:]}" if accessor == "is" else f"get{field_name[:1].upper()}{field_name[1:]}"
        if java_type == "Boolean" and field_name.startswith("is"):
            getter = field_name
        getters_setters.append(f"\n    public {java_type} {getter}() {{\n        return {field_name};\n    }}")
        getters_setters.append(
            f"\n    public void set{field_name[:1].upper()}{field_name[1:]}({java_type} {field_name}) {{\n"
            f"        this.{field_name} = {field_name};\n    }}"
        )

    return render_template(
        SPRING_ENTITY_TEMPLATE,
        **tokens,
        IMPORTS=_java_imports(types),
        FIELDS="\n".join(fields),
        GETTERS_SETTERS="\n".join(getters_setters),
    )


def _java_request_fields(table: dict[str, Any]) -> str:
    clean: list[str] = []
    for column in table_columns(table):
        if is_pk(column):
            continue
        name = column.get("name") or ""
        java_type = _java_type(column)
        nullable = is_nullable(column)
        precision = column_precision(column.get("type") or "")
        annotations: list[str] = []
        if java_type == "String" and not nullable:
            annotations.append("@NotBlank(message = \"is required\")")
        elif java_type != "String" and not nullable:
            annotations.append("@NotNull(message = \"is required\")")
        if java_type == "String" and precision:
            annotations.append(f"@Size(max = {precision})")
        field_name = camel_case(name)
        block = [f"    {a}" for a in annotations]
        block.append(f"    private {java_type} {field_name};")
        clean.append("\n".join(block))
    return "\n\n".join(clean)


def _java_response_fields(table: dict[str, Any]) -> str:
    parts = ["        Long id"]
    for column in table_columns(table):
        if is_pk(column):
            continue
        parts.append(f"        {_java_type(column)} {camel_case(column.get('name') or '')}")
    return ",\n".join(parts)


def _java_apply_lines(table: dict[str, Any]) -> str:
    lines: list[str] = []
    for column in table_columns(table):
        if is_pk(column) or column.get("name") in ("created_at", "updated_at"):
            continue
        field_name = camel_case(column.get("name") or "")
        setter = f"set{field_name[:1].upper()}{field_name[1:]}"
        lines.append(f"        entity.{setter}(request.get{field_name[:1].upper()}{field_name[1:]}());")
    return "\n".join(lines) if lines else "        // no writable fields"


def _java_to_response_lines(table: dict[str, Any]) -> str:
    lines: list[str] = ["                entity.getId()"]
    for column in table_columns(table):
        if is_pk(column):
            continue
        field_name = camel_case(column.get("name") or "")
        getter = "get" + field_name[:1].upper() + field_name[1:]
        lines.append(f"                entity.{getter}()")
    return ",\n".join(lines)


def generate_spring(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tokens = _spring_tokens(context)
    primary = context["primary_table"]
    model_lower = tokens["MODEL_LOWER"]

    entity = _java_entity(primary, tokens)
    request = render_template(SPRING_REQUEST_TEMPLATE, **tokens, FIELDS=_java_request_fields(primary))
    response = render_template(SPRING_RESPONSE_TEMPLATE, **tokens, FIELDS=_java_response_fields(primary))
    service = render_template(
        SPRING_SERVICE_TEMPLATE,
        **tokens,
        APPLY=_java_apply_lines(primary),
        TO_RESPONSE=_java_to_response_lines(primary),
    )

    path = tokens["PACKAGE_PATH"]

    files = {
        "README.md": render_template(SPRING_README, **tokens),
        ".gitignore": SPRING_GITIGNORE,
        ".env.example": render_template(SPRING_ENV_EXAMPLE, **tokens),
        "pom.xml": render_template(SPRING_POM, **tokens),
        "Dockerfile": SPRING_DOCKERFILE,
        "docker-compose.yml": render_template(SPRING_COMPOSE, **tokens),
        "src/main/resources/application.yml": render_template(SPRING_APPLICATION_YML, **tokens),
        "src/test/resources/application-test.yml": SPRING_TEST_PROPS,
        f"src/main/java/{path}/__APP_CLASS__Application.java".replace("__APP_CLASS__", tokens["APP_CLASS"]):
            render_template(SPRING_APPLICATION, **tokens),
        f"src/main/java/{path}/HealthController.java": render_template(SPRING_HEALTH, **tokens),
        f"src/main/java/{path}/common/ApiException.java": render_template(SPRING_API_EXCEPTION, **tokens),
        f"src/main/java/{path}/common/GlobalExceptionHandler.java": render_template(SPRING_EXCEPTION_HANDLER, **tokens),
        f"src/main/java/{path}/config/JwtService.java": render_template(SPRING_JWT_SERVICE, **tokens),
        f"src/main/java/{path}/config/JwtAuthenticationFilter.java": render_template(SPRING_SECURITY_FILTER, **tokens),
        f"src/main/java/{path}/config/SecurityConfig.java": render_template(SPRING_SECURITY_CONFIG, **tokens),
        f"src/main/java/{path}/config/OpenApiConfig.java": render_template(SPRING_OPENAPI_CONFIG, **tokens),
        f"src/main/java/{path}/user/User.java": render_template(SPRING_USER_ENTITY, **tokens),
        f"src/main/java/{path}/user/UserRepository.java": render_template(SPRING_USER_REPOSITORY, **tokens),
        f"src/main/java/{path}/auth/dto/RegisterRequest.java": render_template(SPRING_AUTH_DTOS, **tokens),
        f"src/main/java/{path}/auth/dto/LoginRequest.java": render_template(SPRING_AUTH_LOGIN, **tokens),
        f"src/main/java/{path}/auth/dto/AuthResponse.java": render_template(SPRING_AUTH_RESPONSE, **tokens),
        f"src/main/java/{path}/auth/AuthService.java": render_template(SPRING_AUTH_SERVICE, **tokens),
        f"src/main/java/{path}/auth/AuthController.java": render_template(SPRING_AUTH_CONTROLLER, **tokens),
        f"src/main/java/{path}/{model_lower}/__MODEL__Entity.java".replace("__MODEL__", tokens["MODEL"]): entity,
        f"src/main/java/{path}/{model_lower}/__MODEL__Repository.java".replace("__MODEL__", tokens["MODEL"]):
            render_template(SPRING_REPOSITORY_TEMPLATE, **tokens),
        f"src/main/java/{path}/{model_lower}/dto/__MODEL__Request.java".replace("__MODEL__", tokens["MODEL"]): request,
        f"src/main/java/{path}/{model_lower}/dto/__MODEL__Response.java".replace("__MODEL__", tokens["MODEL"]): response,
        f"src/main/java/{path}/{model_lower}/__MODEL__Service.java".replace("__MODEL__", tokens["MODEL"]): service,
        f"src/main/java/{path}/{model_lower}/__MODEL__Controller.java".replace("__MODEL__", tokens["MODEL"]):
            render_template(SPRING_CONTROLLER_TEMPLATE, **tokens),
        f"src/test/java/{path}/__APP_CLASS__ApplicationTests.java".replace("__APP_CLASS__", tokens["APP_CLASS"]):
            render_template(SPRING_APPLICATION_TESTS, **tokens),
    }
    return files



