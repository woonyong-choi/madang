package madang.desktop.fake

import java.io.File
import java.util.regex.Pattern
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.yaml.snakeyaml.DumperOptions
import org.yaml.snakeyaml.LoaderOptions
import org.yaml.snakeyaml.Yaml
import org.yaml.snakeyaml.constructor.Constructor
import org.yaml.snakeyaml.nodes.Tag
import org.yaml.snakeyaml.representer.Representer
import org.yaml.snakeyaml.resolver.Resolver

/** 계약의 응답 예시 하나. [body]가 null이면 본문이 없다. */
data class ExampleResponse(val status: Int, val body: JsonElement?)

/**
 * core/openapi.yaml의 `examples`로 응답을 만든다.
 *
 * 응답 스키마가 `$ref`면 그 스키마의 첫 예시를, 배열이면 항목 예시 하나를 담은 배열을 쓴다.
 */
class ContractExamples(private val spec: Map<String, Any?>) {

    private val paths: Map<String, Any?> = spec.map("paths")
    private val schemas: Map<String, Any?> = spec.map("components").map("schemas")

    /** [method] [path]에 대한 첫 2xx 응답 예시. 계약에 없는 경로면 null. */
    fun response(method: String, path: String): ExampleResponse? {
        val template = paths.keys.firstOrNull { matches(it, path) } ?: return null
        val operation = paths.map(template).map(method.lowercase())
        if (operation.isEmpty()) return null
        val (code, response) = operation.map("responses").entries
            .firstOrNull { it.key.startsWith("2") } ?: return null
        val schema = (response as? Map<*, *>)?.asMap()?.map("content")
            ?.map("application/json")?.get("schema")
        return ExampleResponse(code.toInt(), schema?.let(::exampleFor))
    }

    /** `Event` oneOf의 각 이벤트 예시(JSON 텍스트). */
    fun events(): List<String> = schemas.map("Event").list("oneOf")
        .mapNotNull { exampleFor(it)?.toString() }

    private fun exampleFor(schema: Any?): JsonElement? {
        val node = (schema as? Map<*, *>)?.asMap() ?: return null
        (node["\$ref"] as? String)?.let { return exampleFor(schemas[it.substringAfterLast('/')]) }
        node.list("examples").firstOrNull()?.let { return toJson(it) }
        node["example"]?.let { return toJson(it) }
        if (node["items"] != null) return exampleFor(node["items"])?.let { JsonArray(listOf(it)) }
        return null
    }

    private fun matches(template: String, path: String): Boolean {
        val expected = template.trim('/').split('/')
        val actual = path.trim('/').split('/')
        return expected.size == actual.size &&
            expected.zip(actual).all { (e, a) -> e.startsWith("{") || e == a }
    }

    companion object {
        fun load(file: File): ContractExamples {
            val options = LoaderOptions()
            val dumper = DumperOptions()
            val yaml =
                Yaml(Constructor(options), Representer(dumper), dumper, options, NoTimestamps())
            return ContractExamples(yaml.load(file.readText()))
        }
    }
}

fun toJson(value: Any?): JsonElement = when (value) {
    null -> JsonNull
    is Map<*, *> -> JsonObject(value.entries.associate { "${it.key}" to toJson(it.value) })
    is List<*> -> JsonArray(value.map(::toJson))
    is Boolean -> JsonPrimitive(value)
    is Number -> JsonPrimitive(value)
    else -> JsonPrimitive(value.toString())
}

/** 날짜처럼 보이는 값도 문자열로 둔다. 계약의 시각과 페이지 id는 모두 문자열이다. */
private class NoTimestamps : Resolver() {
    override fun addImplicitResolver(tag: Tag, regexp: Pattern, first: String?, limit: Int) {
        if (tag != Tag.TIMESTAMP) super.addImplicitResolver(tag, regexp, first, limit)
    }
}

@Suppress("UNCHECKED_CAST")
private fun Map<*, *>.asMap(): Map<String, Any?> = this as Map<String, Any?>

private fun Map<String, Any?>.map(key: String): Map<String, Any?> =
    (this[key] as? Map<*, *>)?.asMap() ?: emptyMap()

private fun Map<String, Any?>.list(key: String): List<Any?> =
    this[key] as? List<Any?> ?: emptyList()
