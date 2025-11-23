"""
Тесты для модуля orchestrator.devflow.

Проверяют структуру DevFlow-сценариев и базовую функциональность.
"""

import pytest

from orchestrator.devflow import (
    DevFlowStepType,
    DevFlowStep,
    DevFlowScenario,
    create_simple_ma_scenario,
)


def test_devflow_step_type_enum():
    """Проверяем, что DevFlowStepType содержит ожидаемые типы."""
    assert DevFlowStepType.CURSOR_TASK == "cursor_task"
    assert DevFlowStepType.RUN_TESTS == "run_tests"
    assert DevFlowStepType.SERVER_UPDATE == "server_update"


def test_devflow_step_creation():
    """Проверяем создание DevFlowStep."""
    step = DevFlowStep(
        type=DevFlowStepType.CURSOR_TASK,
        name="test_step",
        description="Test step description",
        config={"key": "value"},
    )
    
    assert step.type == DevFlowStepType.CURSOR_TASK
    assert step.name == "test_step"
    assert step.description == "Test step description"
    assert step.config == {"key": "value"}


def test_devflow_scenario_creation():
    """Проверяем создание DevFlowScenario."""
    steps = [
        DevFlowStep(
            type=DevFlowStepType.CURSOR_TASK,
            name="step1",
            description="Step 1",
            config={},
        ),
        DevFlowStep(
            type=DevFlowStepType.RUN_TESTS,
            name="step2",
            description="Step 2",
            config={},
        ),
    ]
    
    scenario = DevFlowScenario(
        name="test_scenario",
        description="Test scenario",
        steps=steps,
    )
    
    assert scenario.name == "test_scenario"
    assert scenario.description == "Test scenario"
    assert len(scenario.steps) == 2
    assert scenario.steps[0].name == "step1"
    assert scenario.steps[1].name == "step2"


def test_simple_ma_scenario_structure():
    """Проверяем структуру сценария simple_ma."""
    flow_id = "test-flow-id"
    scenario = create_simple_ma_scenario(flow_id)
    
    # Проверяем базовые поля
    assert scenario.name == "devflow_simple_ma"
    assert "Simple Moving Average" in scenario.description
    assert len(scenario.steps) == 3  # Должно быть 3 шага
    
    # Проверяем типы шагов (все должны быть CURSOR_TASK)
    for step in scenario.steps:
        assert step.type == DevFlowStepType.CURSOR_TASK
        assert "flow_id" in step.config
        assert step.config["flow_id"] == flow_id
        assert "step_number" in step.config
        assert "step_prompt" in step.config
        assert "scenario_name" in step.config
        assert step.config["scenario_name"] == "simple_ma"
    
    # Проверяем порядок шагов
    assert scenario.steps[0].config["step_number"] == 1
    assert scenario.steps[1].config["step_number"] == 2
    assert scenario.steps[2].config["step_number"] == 3
    
    # Проверяем, что промпты не пустые
    for step in scenario.steps:
        assert step.config["step_prompt"], f"Step {step.name} has empty prompt"


def test_simple_ma_scenario_step_names():
    """Проверяем имена шагов в сценарии simple_ma."""
    flow_id = "test-flow-id"
    scenario = create_simple_ma_scenario(flow_id)
    
    # Проверяем, что имена шагов соответствуют ожидаемым
    step_names = [step.name for step in scenario.steps]
    assert "simple_ma_impl" in step_names
    assert "simple_ma_tests" in step_names
    assert "simple_ma_integration" in step_names


def test_simple_ma_scenario_descriptions():
    """Проверяем описания шагов в сценарии simple_ma."""
    flow_id = "test-flow-id"
    scenario = create_simple_ma_scenario(flow_id)
    
    # Проверяем, что описания не пустые
    for step in scenario.steps:
        assert step.description, f"Step {step.name} has empty description"
        assert len(step.description) > 10  # Описание должно быть достаточно подробным

