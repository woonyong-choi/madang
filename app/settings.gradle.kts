rootProject.name = "madang-app"

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
        google()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
        google()
        // 브라우저 탭 엔진(KCEF)이 쓰는 jogamp 라이브러리는 jogamp 저장소에만 있다.
        maven("https://jogamp.org/deployment/maven") {
            content { includeGroupByRegex("org\\.jogamp.*") }
        }
    }
}

include(":shared", ":desktop")
