plugins {
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.compose.multiplatform) apply false
    alias(libs.plugins.openapi.generator) apply false
    alias(libs.plugins.ktlint)
}

val ktlintVersion = libs.versions.ktlint.cli.get()

// 스타일 규칙은 .editorconfig(android_studio 코드 스타일)에 있다.
allprojects {
    apply(plugin = "org.jlleitschuh.gradle.ktlint")

    configure<org.jlleitschuh.gradle.ktlint.KtlintExtension> {
        version.set(ktlintVersion)
        filter {
            exclude { it.file.path.contains("${File.separator}build${File.separator}") }
        }
    }
}
