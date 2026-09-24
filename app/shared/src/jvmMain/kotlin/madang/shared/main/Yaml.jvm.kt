package madang.shared.main

import org.yaml.snakeyaml.LoaderOptions
import org.yaml.snakeyaml.Yaml
import org.yaml.snakeyaml.constructor.SafeConstructor

actual fun loadYaml(content: String): Any? = Yaml(SafeConstructor(LoaderOptions())).load(content)
