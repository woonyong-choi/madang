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

// 패키지에 싣는 동봉 core(scripts/build-core.sh의 PyInstaller onedir)와 제3자 고지.
// Compose는 appResourcesRootDir의 common/과 운영체제 폴더를 앱 리소스 폴더로 합친다.
val coreBundle: File = coreProject.resolve("dist/madang-core")
val appResources = layout.buildDirectory.dir("app-resources")
val osResourceDir: String = System.getProperty("os.name").lowercase().let {
    when {
        it.contains("mac") -> "macos"
        it.contains("win") -> "windows"
        else -> "linux"
    }
}

val prepareCoreBundle by tasks.registering(Sync::class) {
    into(appResources)
    from(rootProject.projectDir.resolve("../THIRD_PARTY_NOTICES.md")) { into("common") }
    from(coreBundle) { into("$osResourceDir/madang-core") }
}

tasks.matching { it.name == "prepareAppResources" }.configureEach {
    dependsOn(prepareCoreBundle)
}

// 개발 실행은 동봉 core 없이도 되지만, 앱 이미지(dmg·msi의 바탕)는 core 없이 만들지 않는다.
// 앱 이미지로 리소스를 복사할 때 실행 비트가 빠지므로 동봉 core 실행 파일에 되돌린다.
tasks.matching { it.name in setOf("createDistributable", "createReleaseDistributable") }
    .configureEach {
        doFirst {
            check(coreBundle.resolve("madang").canExecute()) {
                "core bundle missing: run scripts/build-core.sh first (${coreBundle.path})"
            }
        }
        doLast {
            outputs.files.asFileTree
                .matching { include("**/resources/madang-core/madang") }
                .forEach { it.setExecutable(true, false) }
        }
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
            appResourcesRootDir.set(appResources)
            // jlink 런타임 모듈. KCEF(JCEF)가 jdk.unsupported를, 엔진 번들 내려받기(TLS)가
            // jdk.crypto.ec를 쓴다. 나머지는 suggestRuntimeModules 결과다.
            modules("java.instrument", "java.management", "jdk.unsupported", "jdk.crypto.ec")
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
