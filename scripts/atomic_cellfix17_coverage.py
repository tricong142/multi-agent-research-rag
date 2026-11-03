"""Bind coverage to exact legal observation spans without discarding punctuation."""


def bind_coverage(schema, context):
    props = schema["properties"]
    observation = props["observations"]["items"]
    members = {member for branch in observation.get("anyOf", [observation])
               for member in branch["properties"]["member"].get("enum", [])
               if isinstance(member, str) and member and member in context}
    coverage = props["coverage"]
    kept = []
    for branch in coverage.get("anyOf", [coverage]):
        fields = branch["properties"]
        names = fields["members"]
        complete = fields["complete"]
        required = (names.get("minItems", 0) > 0 or complete.get("const") is True
                    or complete.get("enum") == [True])
        if names.get("maxItems") == 0:
            if required:
                continue
            fields["complete"] = {"const": False}
            names["items"] = {"type": "string"}
            kept.append(branch)
            continue
        original = names["items"].get("enum", members)
        allowed = sorted(members.intersection(original))
        if allowed:
            names["items"] = {"type": "string", "enum": allowed}
        else:
            if required:
                continue
            fields["complete"] = {"const": False}
            names.update(minItems=0, maxItems=0, items={"type": "string"})
        kept.append(branch)
    if not kept:
        raise ValueError("unrepresentable_coverage_members")
    props["coverage"] = kept[0] if len(kept) == 1 else {"anyOf": kept}
    return schema
