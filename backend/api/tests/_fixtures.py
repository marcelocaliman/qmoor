"""Helpers compartilhados por testes de cases/solve/moor."""
from __future__ import annotations


# Payload válido (BC-01 like) pronto para POST /cases
BC01_LIKE_INPUT = {
    "name": "BC-01 — catenária pura suspensa",
    "description": "Wire rope 3in, lâmina 300 m, T_fl=785 kN",
    "segments": [
        {
            "length": 450.0,
            "w": 201.10404 ,  # 13.78 lbf/ft convertido
            "EA": 3.425e7,
            "MBL": 3.78e6,
            "category": "Wire",
            "line_type": "IWRCEIPS",
        }
    ],
    "boundary": {
        "h": 300.0,
        "mode": "Tension",
        "input_value": 785000.0,
        "startpoint_depth": 0.0,
        "endpoint_grounded": True,
    },
    "seabed": {"mu": 0.0},
    "criteria_profile": "MVP_Preliminary",
}


BC04_LIKE_INPUT = {
    "name": "BC-04 elástico suspenso",
    "description": "IWRCEIPS 3in, lâmina 1000 m, T_fl=150 t, mu=0.30",
    "segments": [
        {
            "length": 1800.0,
            "w": 201.10404,
            "EA": 34.25e6,
            "MBL": 3.78e6,
            "category": "Wire",
            "line_type": "IWRCEIPS",
        }
    ],
    "boundary": {
        "h": 1000.0,
        "mode": "Tension",
        "input_value": 150 * 9806.65,  # 150 t em N
    },
    "seabed": {"mu": 0.30},
    "criteria_profile": "MVP_Preliminary",
}
