plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.compose.multiplatform)
    alias(libs.plugins.openapi.generator)
}

// core와의 계약 파일. -Pmadang.openapiSpec=<경로>로 다른 파일에서 생성할 수 있다.
val openApiSpec: File = providers.gradleProperty("madang.openapiSpec")
    .map { file(it) }
    .getOrElse(rootProject.file("../core/openapi.yaml"))
val openApiOutput = layout.buildDirectory.dir("generated/openapi")

kotlin {
    jvmToolchain(21)

    jvm()

    sourceSets {
        commonMain {
            // 작업 출력에서 소스 디렉터리를 얻으므로 컴파일 전에 생성이 자동으로 돈다.
            kotlin.srcDir(
                tasks.named("openApiGenerate").map {
                    openApiOutput.get().dir("src/commonMain/kotlin")
                }
            )
            dependencies {
                implementation(libs.compose.runtime)
                implementation(libs.compose.foundation)
                implementation(libs.compose.ui)
                implementation(libs.compose.material3)
                implementation(libs.compose.material.icons.extended)
                implementation(libs.markdown.renderer.m3)
                implementation(libs.kotlinx.datetime)
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
                implementation(libs.snakeyaml)
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
    doFirst { delete(openApiOutput) }
}

// Kotlin Multiplatform에는 단순 `test` 작업이 없으므로 JVM 테스트의 별칭으로 둔다.
if (tasks.findByName("test") == null) {
    tasks.register("test") {
        group = "verification"
        description = "Runs the common tests on the JVM target."
        dependsOn("jvmTest")
    }
}
