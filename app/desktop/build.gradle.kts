import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.compose.multiplatform)
}

kotlin {
    jvmToolchain(21)
}

dependencies {
    implementation(project(":shared"))
    implementation(compose.desktop.currentOs)
    implementation(libs.kotlinx.coroutines.swing)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.mock)
    implementation(libs.snakeyaml)

    testImplementation(kotlin("test"))
    testImplementation(libs.kotlinx.coroutines.test)
}

// 창 아이콘에 쓰는 PNG만 jar에 넣는다. icns·ico는 패키징에서만 쓴다.
tasks.processResources {
    from("icons") { include("icon.png") }
}

// 개발 실행과 테스트는 저장소의 core 프로젝트와 계약 파일을 쓴다.
val coreProject: File = rootProject.projectDir.resolve("../core").canonicalFile
val openApiSpec: File = coreProject.resolve("openapi.yaml")

tasks.withType<JavaExec>().configureEach {
    systemProperty("madang.coreProject", coreProject.path)
    systemProperty("madang.openapiSpec", openApiSpec.path)
}

tasks.test {
    systemProperty("madang.openapiSpec", openApiSpec.path)
}

compose.desktop {
    application {
        mainClass = "madang.desktop.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Dmg, TargetFormat.Msi)
            packageName = "Madang"
            packageVersion = "1.0.0"

            macOS {
                iconFile.set(project.file("icons/icon.icns"))
            }
            windows {
                iconFile.set(project.file("icons/icon.ico"))
            }
            linux {
                iconFile.set(project.file("icons/icon.png"))
            }
        }
    }
}
