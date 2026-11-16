from .critic_contracts import follow_up_suffix
from .role_prompts import chatmate_candidate_attacker_system_instruction, chatmate_candidate_generation_guidelines


def generation_parts(spec, method, context, *, include_method_constraint=True):
    suffix = follow_up_suffix(context)
    return (chatmate_candidate_attacker_system_instruction(spec, method) + suffix,
            [*chatmate_candidate_generation_guidelines(spec, method, include_method_constraint=include_method_constraint), suffix],
            spec.attack_objective + suffix)
