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
    implementation(libs.kcef)

    testImplementation(kotlin("test"))
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.compose.material3)
    testImplementation(libs.kotlinx.datetime)
}

// 문서 탭 렌더러. 게시와 같은 `templates/_runtime` 파일을 jar에 싣는다(DocumentRuntime.FILES).
val documentRuntime: File = rootProject.projectDir.resolve("../templates/_runtime").canonicalFile

// 창 아이콘에 쓰는 PNG만 jar에 넣는다. icns·ico는 패키징에서만 쓴다.
tasks.processResources {
    from("icons") { include("icon.png") }
    from(documentRuntime) {
        include(
            "app.html",
            "app.js",
            "document.js",
            "document.css",
            "vendor/marked.umd.js",
            "vendor/marked.LICENSE",
            "THIRD_PARTY_NOTICES.md"
        )
        into("madang-runtime")
    }
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
    // 레이어 0 스크린샷 테스트가 PNG를 쓰는 곳.
    systemProperty(
        "madang.screenshotDir",
        layout.buildDirectory.dir("screenshots").get().asFile.path
    )
}

compose.desktop {
    application {
        mainClass = "madang.desktop.MainKt"

        // 브라우저 탭 엔진(KCEF)이 AWT 내부에 접근한다.
        jvmArgs("--add-opens", "java.desktop/sun.awt=ALL-UNNAMED")
        jvmArgs("--add-opens", "java.desktop/java.awt.peer=ALL-UNNAMED")
        if (System.getProperty("os.name").lowercase().contains("mac")) {
            jvmArgs("--add-opens", "java.desktop/sun.lwawt=ALL-UNNAMED")
            jvmArgs("--add-opens", "java.desktop/sun.lwawt.macosx=ALL-UNNAMED")
        }

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
