plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.compose.multiplatform)
    alias(libs.plugins.openapi.generator)
}

// Contract with core. Override with -Pmadang.openapiSpec=<path> to generate from another file.
val openApiSpec: File = providers.gradleProperty("madang.openapiSpec")
    .map { file(it) }
    .getOrElse(rootProject.file("../core/openapi.yaml"))
val hasOpenApiSpec = openApiSpec.isFile
val openApiOutput = layout.buildDirectory.dir("generated/openapi")

kotlin {
    jvmToolchain(21)

    jvm()

    sourceSets {
        commonMain {
            if (hasOpenApiSpec) {
                kotlin.srcDir(openApiOutput.map { it.dir("src/commonMain/kotlin") })
            }
            dependencies {
                implementation(libs.compose.runtime)
                implementation(libs.compose.foundation)
                implementation(libs.compose.ui)
                implementation(libs.compose.material3)
                implementation(libs.kotlinx.coroutines.core)
                implementation(libs.kotlinx.serialization.json)
                implementation(libs.ktor.client.core)
                implementation(libs.ktor.client.content.negotiation)
                implementation(libs.ktor.client.websockets)
                implementation(libs.ktor.serialization.kotlinx.json)
            }
        }
        commonTest {
            dependencies {
                implementation(kotlin("test"))
                implementation(libs.kotlinx.coroutines.test)
                implementation(libs.ktor.client.mock)
            }
        }
        jvmMain {
            dependencies {
                implementation(libs.ktor.client.cio)
            }
        }
    }
}

openApiGenerate {
    generatorName.set("kotlin")
    library.set("multiplatform")
    inputSpec.set(openApiSpec.path)
    outputDir.set(openApiOutput.map { it.asFile.path })
    packageName.set("madang.api")
    apiPackage.set("madang.api.client")
    modelPackage.set("madang.api.model")
    generateApiTests.set(false)
    generateModelTests.set(false)
    generateApiDocumentation.set(false)
    generateModelDocumentation.set(false)
    configOptions.set(
        mapOf(
            "dateLibrary" to "string",
            "enumPropertyNaming" to "UPPERCASE",
            "omitGradleWrapper" to "true",
            "omitGradlePluginVersions" to "true"
        )
    )
}

tasks.named("openApiGenerate") {
    onlyIf("core/openapi.yaml exists") { hasOpenApiSpec }
    doFirst { delete(openApiOutput) }
}

if (hasOpenApiSpec) {
    tasks.matching { it.name.startsWith("compileKotlin") }.configureEach {
        dependsOn("openApiGenerate")
    }
}

// Kotlin Multiplatform has no plain `test` task; alias it to the JVM tests.
if (tasks.findByName("test") == null) {
    tasks.register("test") {
        group = "verification"
        description = "Runs the common tests on the JVM target."
        dependsOn("jvmTest")
    }
}
