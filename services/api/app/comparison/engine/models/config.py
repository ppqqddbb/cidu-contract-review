from pydantic import BaseModel


class ComparisonProfile(BaseModel):
    min_anchor_chars: int = 24
    coarse_target_chars: int = 1800
    coarse_max_chars: int = 5000
    fine_target_chars: int = 320
    fine_max_chars: int = 900
    block_target_min_chars: int = 200
    block_target_max_chars: int = 1200
    block_hard_max_chars: int = 1800
    candidate_top_k: int = 5
    candidate_min_score: float = 0.45
    block_match_threshold: float = 0.68
    compound_match_threshold: float = 0.84
    max_compound_span: int = 3
    line_match_threshold: float = 0.62
    ignore_headers_footers: bool = True
    unicode_normalization: str = "NFC"
    render_dpi: int = 160
    max_group_old: int = 3
    max_group_new: int = 3
    hard_reject: float = 0.55
    base_gap_cost: float = 0.35
    length_weight: float = 0.04
    alignment_band: int = 30
    max_length_ratio_for_match: float = 6.0
    sentence_match_threshold: float = 0.78
    sentence_max_merge: int = 2
    split_merge_threshold: float = 0.85
    ignore_pure_numbering_changes: bool = True
    detect_move: bool = True
    show_move: bool = False

