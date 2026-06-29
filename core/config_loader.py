"""
配置加载器 - 支持配置继承、合并和热加载
"""

from __future__ import annotations

import copy
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml


# 默认配置目录
DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


class ConfigLoader:
    """配置加载器，支持继承、合并和热加载"""

    def __init__(self, config_dir: str | Path | None = None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self._cache: dict[str, dict] = {}
        self._cache_time: dict[str, float] = {}
        self.cache_ttl = 300  # 缓存过期时间（秒）
        self._watch_interval = 30
        self._last_watch_time = 0

    # ============================================================
    # 公共 API
    # ============================================================

    def load_brand(self, brand_id: str) -> dict[str, Any]:
        """加载品牌配置，支持继承链"""
        return self._load_config_with_inheritance("brands", brand_id)

    def load_template(self, template_id: str) -> dict[str, Any]:
        """加载模板映射配置"""
        return self._load_config("templates", template_id)

    def load_prompt_engine(self) -> dict[str, Any]:
        """加载 Prompt 引擎配置"""
        return self._load_config("prompts", "prompt_engine")

    def list_brands(self) -> list[dict[str, Any]]:
        """列出所有可用品牌"""
        brands_dir = self.config_dir / "brands"
        brands = []
        for f in sorted(brands_dir.glob("*.yaml")):
            brand_id = f.stem
            try:
                config = self.load_brand(brand_id)
                brands.append({
                    "brand_id": brand_id,
                    "brand_name": config.get("brand_name", brand_id),
                    "version": config.get("version", "unknown"),
                    "description": config.get("description", ""),
                })
            except Exception as e:
                print(f"Warning: failed to load brand {brand_id}: {e}")
        return brands

    def invalidate_cache(self, config_type: str | None = None) -> None:
        """使缓存失效"""
        if config_type is None:
            self._cache.clear()
            self._cache_time.clear()
        else:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{config_type}.")]
            for k in keys_to_remove:
                del self._cache[k]
                del self._cache_time[k]

    # ============================================================
    # 内部方法
    # ============================================================

    def _load_config_with_inheritance(self, config_type: str, config_id: str) -> dict[str, Any]:
        """加载配置并处理继承链"""
        cache_key = f"{config_type}.{config_id}"

        # 检查缓存
        if self._is_cache_valid(cache_key):
            return copy.deepcopy(self._cache[cache_key])

        # 加载当前配置
        config = self._load_config(config_type, config_id)

        # 处理继承
        inherits = config.get("inherits")
        if inherits:
            parent_config = self._load_config_with_inheritance(config_type, inherits)
            config = self._merge_configs(parent_config, config)
            # 移除 inherits 字段，避免循环
            config.pop("inherits", None)

        # 缓存
        self._cache[cache_key] = config
        self._cache_time[cache_key] = time.time()

        return copy.deepcopy(config)

    def _load_config(self, config_type: str, config_id: str) -> dict[str, Any]:
        """从文件加载单个配置"""
        config_path = self.config_dir / config_type / f"{config_id}.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if config is None:
            config = {}

        # 添加元数据
        config["_config_path"] = str(config_path)
        config["_config_id"] = config_id

        return config

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache:
            return False

        cache_time = self._cache_time.get(cache_key, 0)
        if time.time() - cache_time > self.cache_ttl:
            return False

        # 检查文件是否修改
        config_path = self._cache[cache_key].get("_config_path")
        if config_path and Path(config_path).exists():
            mtime = Path(config_path).stat().st_mtime
            if mtime > cache_time:
                return False

        return True

    # ============================================================
    # 配置合并逻辑
    # ============================================================

    def _merge_configs(self, parent: dict, child: dict) -> dict:
        """递归合并配置，子配置优先"""
        result = copy.deepcopy(parent)

        for key, child_value in child.items():
            if key.startswith("_"):
                # 元数据直接覆盖
                result[key] = child_value
                continue

            if key not in result:
                result[key] = copy.deepcopy(child_value)
                continue

            parent_value = result[key]

            if isinstance(parent_value, dict) and isinstance(child_value, dict):
                result[key] = self._merge_configs(parent_value, child_value)
            elif isinstance(parent_value, list) and isinstance(child_value, list):
                # 列表合并策略：根据内容类型决定
                result[key] = self._merge_lists(parent_value, child_value, key)
            else:
                # 标量直接覆盖
                result[key] = copy.deepcopy(child_value)

        return result

    def _merge_lists(self, parent_list: list, child_list: list, context_key: str) -> list:
        """合并列表，根据上下文决定策略"""
        # 策略 1: 如果列表元素是字典且有 field 键（字段定义），按 field 合并
        if parent_list and isinstance(parent_list[0], dict) and 'field' in parent_list[0]:
            return self._merge_field_lists(parent_list, child_list)

        # 策略 2: 如果列表元素是字典且有 id 键（章节定义），按 id 合并
        if parent_list and isinstance(parent_list[0], dict) and 'id' in parent_list[0]:
            return self._merge_id_lists(parent_list, child_list)

        # 策略 3: 简单列表（如 focus_areas, must_follow），子配置完全覆盖
        return copy.deepcopy(child_list)

    def _merge_field_lists(self, parent_list: list, child_list: list) -> list:
        """按 field 合并字段定义列表
        
        策略：
        - 子配置中的字段定义优先（覆盖父配置）
        - 如果子配置中没有某个字段，保留父配置中的定义
        - 如果字段在子配置和父配置中都存在，合并（子配置优先）
        
        注意：字段可能在不同类别中（如父配置 optional 中的 req_id，
        子配置 required 中的 req_id），合并后统一放入子配置的类别。
        """
        parent_map = {item["field"]: item for item in parent_list if isinstance(item, dict) and "field" in item}
        result = []
        processed = set()

        # 先处理子配置的字段
        for child_item in child_list:
            if not isinstance(child_item, dict) or "field" not in child_item:
                result.append(copy.deepcopy(child_item))
                continue

            field_name = child_item["field"]
            processed.add(field_name)

            if field_name in parent_map:
                # 合并字段定义（子配置优先）
                merged = self._merge_configs(parent_map[field_name], child_item)
                result.append(merged)
            else:
                # 新增字段
                result.append(copy.deepcopy(child_item))

        return result

    def _merge_id_lists(self, parent_list: list, child_list: list) -> list:
        """按 id 合并章节/模块定义列表"""
        parent_map = {item["id"]: item for item in parent_list if isinstance(item, dict) and "id" in item}
        result = []
        processed = set()

        for child_item in child_list:
            if not isinstance(child_item, dict) or "id" not in child_item:
                result.append(copy.deepcopy(child_item))
                continue

            item_id = child_item["id"]
            processed.add(item_id)

            if item_id in parent_map:
                merged = self._merge_configs(parent_map[item_id], child_item)
                result.append(merged)
            else:
                result.append(copy.deepcopy(child_item))

        # 添加父配置中未被覆盖的项
        for parent_item in parent_list:
            if isinstance(parent_item, dict) and "id" in parent_item:
                if parent_item["id"] not in processed:
                    result.append(copy.deepcopy(parent_item))

        return result


# ============================================================
# 配置验证
# ============================================================

class ConfigValidator:
    """配置验证器"""

    def __init__(self, loader: ConfigLoader):
        self.loader = loader
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_brand(self, brand_id: str) -> bool:
        """验证品牌配置"""
        self.errors = []
        self.warnings = []

        try:
            config = self.loader.load_brand(brand_id)
        except Exception as e:
            self.errors.append(f"Failed to load brand config: {e}")
            return False

        # 检查必填字段
        if not config.get("brand_id"):
            self.errors.append("brand_id is required")

        if not config.get("brand_name"):
            self.errors.append("brand_name is required")

        # 检查字段唯一性
        fields = config.get("fields", {})
        all_fields = []
        for category in ["required", "optional", "hidden"]:
            all_fields.extend(fields.get(category, []))

        field_names = [f.get("field") for f in all_fields if isinstance(f, dict)]
        duplicates = [name for name in set(field_names) if field_names.count(name) > 1]
        if duplicates:
            self.errors.append(f"Duplicate field names: {duplicates}")

        # 检查模板映射
        template_mapping = config.get("template_mapping", {})
        if template_mapping.get("use_client_template"):
            path = template_mapping.get("client_template_path")
            if not path:
                self.errors.append("client_template_path is required when use_client_template is true")

        # 检查导出配置
        export = config.get("export", {})
        if not export.get("filename_template"):
            self.warnings.append("filename_template is not set, will use default")

        return len(self.errors) == 0

    def validate_template(self, template_id: str) -> bool:
        """验证模板映射配置"""
        self.errors = []
        self.warnings = []

        try:
            config = self.loader.load_template(template_id)
        except Exception as e:
            self.errors.append(f"Failed to load template config: {e}")
            return False

        # 检查必填字段
        if not config.get("template_id"):
            self.errors.append("template_id is required")

        brand_id = config.get("brand_id")
        if not brand_id:
            self.errors.append("brand_id is required")
        else:
            # 检查 brand_id 是否存在
            try:
                self.loader.load_brand(brand_id)
            except FileNotFoundError:
                self.errors.append(f"brand_id '{brand_id}' does not exist")

        # 检查字段映射有效性
        field_mappings = config.get("field_mappings", [])
        target_pattern = re.compile(r"^(table\.\d+(\.row\.\d+(\.cell\.\d+)?)?|paragraph\.\d+)$")

        for mapping in field_mappings:
            if not isinstance(mapping, dict):
                continue

            target = mapping.get("target", "")
            if not target_pattern.match(target):
                self.errors.append(f"Invalid target format: {target}")

        return len(self.errors) == 0


# ============================================================
# 便捷函数
# ============================================================

def get_loader(config_dir: str | Path | None = None) -> ConfigLoader:
    """获取配置加载器实例"""
    env_dir = os.environ.get("GENERIC_REPORT_CONFIG_DIR")
    if env_dir:
        config_dir = env_dir
    return ConfigLoader(config_dir)


def load_brand(brand_id: str, config_dir: str | Path | None = None) -> dict:
    """便捷函数：加载品牌配置"""
    return get_loader(config_dir).load_brand(brand_id)


def load_template(template_id: str, config_dir: str | Path | None = None) -> dict:
    """便捷函数：加载模板配置"""
    return get_loader(config_dir).load_template(template_id)


# ============================================================
# CLI 入口
# ============================================================

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Config loader and validator")
    parser.add_argument("--validate", help="Validate a brand config by ID")
    parser.add_argument("--list", action="store_true", help="List all brands")
    parser.add_argument("--show", help="Show a brand config by ID")
    parser.add_argument("--config-dir", help="Config directory path")
    args = parser.parse_args()

    loader = get_loader(args.config_dir)

    if args.list:
        brands = loader.list_brands()
        print(f"Found {len(brands)} brand(s):")
        for b in brands:
            print(f"  - {b['brand_id']}: {b['brand_name']} (v{b['version']})")
        sys.exit(0)

    if args.validate:
        validator = ConfigValidator(loader)
        is_valid = validator.validate_brand(args.validate)
        if is_valid:
            print(f"[OK] Brand config '{args.validate}' is valid")
            if validator.warnings:
                for w in validator.warnings:
                    print(f"  [WARN] {w}")
        else:
            print(f"[FAIL] Brand config '{args.validate}' has errors:")
            for e in validator.errors:
                print(f"  - {e}")
        sys.exit(0 if is_valid else 1)

    if args.show:
        import json
        config = loader.load_brand(args.show)
        print(json.dumps(config, ensure_ascii=False, indent=2))
        sys.exit(0)

    parser.print_help()
