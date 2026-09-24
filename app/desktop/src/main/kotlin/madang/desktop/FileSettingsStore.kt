package madang.desktop

import java.io.File
import kotlinx.serialization.json.Json
import madang.shared.settings.AppSettings
import madang.shared.settings.AppSettingsStore

/** 앱 설정을 JSON 파일 하나에 둔다. 읽을 수 없으면 기본값을 쓴다. */
class FileSettingsStore(private val file: File) : AppSettingsStore {

    private val json = Json {
        ignoreUnknownKeys = true
        prettyPrint = true
    }

    override fun load(): AppSettings = runCatching {
        json.decodeFromString(AppSettings.serializer(), file.readText())
    }.getOrDefault(AppSettings())

    override fun save(settings: AppSettings) {
        file.parentFile?.mkdirs()
        val temp = File(file.parentFile, file.name + ".tmp")
        temp.writeText(json.encodeToString(AppSettings.serializer(), settings))
        if (!temp.renameTo(file)) {
            file.writeText(temp.readText())
            temp.delete()
        }
    }
}
