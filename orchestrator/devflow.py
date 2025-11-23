"""
DevFlow v1.0 - Расширяемый модуль для многошаговых DevFlow-пайплайнов.

Этот модуль предоставляет архитектуру для создания и выполнения DevFlow-сценариев,
которые могут включать шаги типа CURSOR_TASK, RUN_TESTS, SERVER_UPDATE и другие.

Основные компоненты:
- DevFlowStepType: типы шагов (CURSOR_TASK, RUN_TESTS, SERVER_UPDATE)
- DevFlowStep: описание одного шага сценария
- DevFlowScenario: полный сценарий из нескольких шагов
- run_devflow_scenario: функция для выполнения сценария

Использование:

1. Создание сценария:
    from orchestrator.devflow import create_simple_ma_scenario
    scenario = create_simple_ma_scenario(flow_id="unique-flow-id")

2. Выполнение сценария (последовательно, без подтверждений):
    await run_devflow_scenario(
        scenario=scenario,
        chat_id=chat_id,
        send_telegram_message=send_telegram_message,
        run_cursor_task_for_step=run_cursor_task_for_step,
        run_tests_for_step=run_tests_for_step,
        run_server_update_for_step=run_server_update_for_step,
        logger=logger,
    )

3. Добавление нового сценария (например, для RSI):
    - Создайте функцию create_rsi_scenario(flow_id: str) -> DevFlowScenario
    - Определите шаги с типами DevFlowStepType
    - Добавьте обработчики в run_cursor_task_for_step (если нужны специфичные для RSI)

Текущая реализация:
- simple_ma_scenario использует существующую систему подтверждений через DevFlowSession
- Обработчик /devflow_simple_ma в telegram_bot.py использует новую архитектуру для получения
  информации о шагах, но сохраняет логику подтверждений для совместимости
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from orchestrator.cursor_client import create_devflow_step_agent

logger = logging.getLogger("orchestrator.devflow")


class DevFlowStepType(str, Enum):
    """Типы шагов DevFlow-сценария."""

    CURSOR_TASK = "cursor_task"
    RUN_TESTS = "run_tests"
    SERVER_UPDATE = "server_update"


@dataclass
class DevFlowStep:
    """Описание одного шага DevFlow-сценария."""

    type: DevFlowStepType
    name: str
    description: str
    config: Dict[str, Any]


@dataclass
class DevFlowScenario:
    """Полный DevFlow-сценарий из нескольких шагов."""

    name: str
    description: str
    steps: List[DevFlowStep]


# ============================================================================
# Функции-обёртки для выполнения конкретных типов шагов
# ============================================================================


async def run_cursor_task_for_simple_ma(step: DevFlowStep, chat_id: str) -> None:
    """
    Использует существующий клиент Cursor Cloud для выполнения задачи по simple_ma.

    Должен опираться на текущую логику, которая уже работала.
    """
    logger.info(
        "DevFlow: executing CURSOR_TASK step '%s' for chat_id=%s",
        step.name,
        chat_id,
    )

    # Извлекаем необходимые параметры из config
    flow_id = step.config.get("flow_id", "")
    step_number = step.config.get("step_number", 1)
    step_prompt = step.config.get("step_prompt", "")

    if not step_prompt:
        raise ValueError(
            f"DevFlow step '{step.name}': missing 'step_prompt' in config"
        )

    if not flow_id:
        raise ValueError(
            f"DevFlow step '{step.name}': missing 'flow_id' in config"
        )

    # Создаём Cursor агента для этого шага
    agent_id = await create_devflow_step_agent(
        chat_id=chat_id,
        flow_id=flow_id,
        step=step_number,
        step_prompt=step_prompt,
    )

    logger.info(
        "DevFlow: Cursor agent created for step '%s': agent_id=%s",
        step.name,
        agent_id,
    )

    # Возвращаемся - агент будет работать асинхронно, результат придёт через webhook


async def run_tests_default(step: DevFlowStep, chat_id: str) -> bool:
    """
    Запускает тесты проекта.

    Используй тот же механизм, который сейчас используется в DevFlow simple_ma.
    Верни True, если все тесты прошли, иначе False.
    """
    logger.info(
        "DevFlow: executing RUN_TESTS step '%s' for chat_id=%s",
        step.name,
        chat_id,
    )

    # Извлекаем команду из config (по умолчанию pytest)
    test_command = step.config.get("command", "pytest")
    test_args = step.config.get("args", [])

    # Формируем полную команду
    if isinstance(test_args, str):
        # Если args - строка, разбиваем по пробелам
        cmd_parts = [test_command] + test_args.split()
    elif isinstance(test_args, list):
        cmd_parts = [test_command] + test_args
    else:
        cmd_parts = [test_command]

    logger.info(
        "DevFlow: running test command: %s",
        " ".join(cmd_parts),
    )

    try:
        # Запускаем команду
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=300,  # 5 минут максимум
        )

        if result.returncode == 0:
            logger.info(
                "DevFlow: tests passed for step '%s'",
                step.name,
            )
            return True
        else:
            logger.error(
                "DevFlow: tests failed for step '%s':\nstdout=%s\nstderr=%s",
                step.name,
                result.stdout[:500],
                result.stderr[:500],
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error(
            "DevFlow: test command timed out for step '%s'",
            step.name,
        )
        return False
    except Exception as e:
        logger.exception(
            "DevFlow: error running tests for step '%s'",
            step.name,
        )
        return False


async def run_server_update_default(step: DevFlowStep, chat_id: str) -> bool:
    """
    Вызывает существующий батник/скрипт обновления сервера (pull + restart).

    Ничего не меняй в путях и командной строке — просто используй текущую рабочую логику.
    Верни True, если всё ок, иначе False.
    """
    logger.info(
        "DevFlow: executing SERVER_UPDATE step '%s' for chat_id=%s",
        step.name,
        chat_id,
    )

    # Извлекаем путь к батнику из config (по умолчанию push_to_github_pro.bat)
    batch_path = step.config.get(
        "batch_path", "C:\\Bot\\trading-ai-lab\\push_to_github_pro.bat"
    )

    logger.info(
        "DevFlow: running server update batch: %s",
        batch_path,
    )

    try:
        # Запускаем батник
        result = subprocess.run(
            [batch_path],
            capture_output=True,
            text=True,
            timeout=120,  # 2 минуты максимум
            shell=True,  # Для .bat файлов на Windows
        )

        if result.returncode == 0:
            logger.info(
                "DevFlow: server update completed for step '%s'",
                step.name,
            )
            return True
        else:
            logger.error(
                "DevFlow: server update failed for step '%s':\nstdout=%s\nstderr=%s",
                step.name,
                result.stdout[:500],
                result.stderr[:500],
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error(
            "DevFlow: server update timed out for step '%s'",
            step.name,
        )
        return False
    except Exception as e:
        logger.exception(
            "DevFlow: error running server update for step '%s'",
            step.name,
        )
        return False


# ============================================================================
# Диспетчеризация шагов по типу
# ============================================================================


async def run_cursor_task_for_step(step: DevFlowStep, chat_id: str) -> None:
    """
    Диспетчер для выполнения CURSOR_TASK шагов.

    Пока что поддерживаем только simple_ma по name/или scenario.name.
    В будущем можно расширить для RSI/MACD и т.д.
    """
    # Определяем, какой обработчик использовать
    scenario_name = step.config.get("scenario_name", "")

    if scenario_name == "simple_ma" or step.name.startswith("simple_ma"):
        await run_cursor_task_for_simple_ma(step, chat_id)
    else:
        # Fallback на simple_ma, если не указано
        logger.warning(
            "DevFlow: unknown scenario '%s', using simple_ma handler",
            scenario_name,
        )
        await run_cursor_task_for_simple_ma(step, chat_id)


async def run_tests_for_step(step: DevFlowStep, chat_id: str) -> bool:
    """Диспетчер для выполнения RUN_TESTS шагов."""
    return await run_tests_default(step, chat_id)


async def run_server_update_for_step(step: DevFlowStep, chat_id: str) -> bool:
    """Диспетчер для выполнения SERVER_UPDATE шагов."""
    return await run_server_update_default(step, chat_id)


# ============================================================================
# Основная функция выполнения сценария
# ============================================================================


async def run_devflow_scenario(
    scenario: DevFlowScenario,
    chat_id: str,
    send_telegram_message: Callable[[str, str], Awaitable[None]],
    run_cursor_task_for_step: Callable[[DevFlowStep, str], Awaitable[None]],
    run_tests_for_step: Callable[[DevFlowStep, str], Awaitable[bool]],
    run_server_update_for_step: Callable[[DevFlowStep, str], Awaitable[bool]],
    logger: Optional[Any] = None,
) -> None:
    """
    Выполняет DevFlow-сценарий по шагам.

    Для каждого шага:
    1. Отправляет сообщение о старте шага в Telegram
    2. Логирует старт шага
    3. Выполняет шаг в зависимости от его типа
    4. Обрабатывает ошибки и останавливает сценарий при необходимости
    5. Отправляет сообщение о завершении шага

    Args:
        scenario: DevFlow-сценарий для выполнения
        chat_id: ID чата Telegram
        send_telegram_message: Функция для отправки сообщений в Telegram
        run_cursor_task_for_step: Функция для выполнения CURSOR_TASK шагов
        run_tests_for_step: Функция для выполнения RUN_TESTS шагов
        run_server_update_for_step: Функция для выполнения SERVER_UPDATE шагов
        logger: Логгер (опционально, если None - используется модульный logger)
    """
    if logger is None:
        logger_instance = logging.getLogger("orchestrator.devflow")
    else:
        logger_instance = logger

    total_steps = len(scenario.steps)

    logger_instance.info(
        "DevFlow: starting scenario '%s' for chat_id=%s (total steps: %d)",
        scenario.name,
        chat_id,
        total_steps,
    )

    # Отправляем начальное сообщение
    await send_telegram_message(
        chat_id,
        f"🚀 DevFlow '{scenario.name}': запускаю сценарий ({total_steps} шагов)",
    )

    for step_index, step in enumerate(scenario.steps, start=1):
        step_name = step.name
        step_description = step.description

        # Сообщение о старте шага
        start_message = (
            f"🚀 Шаг {step_index}/{total_steps}: {step_name}\n"
            f"{step_description}"
        )
        await send_telegram_message(chat_id, start_message)

        logger_instance.info(
            "DevFlow: starting step %d/%d: %s (type=%s)",
            step_index,
            total_steps,
            step_name,
            step.type,
        )

        try:
            # Выполняем шаг в зависимости от типа
            if step.type == DevFlowStepType.CURSOR_TASK:
                await run_cursor_task_for_step(step, chat_id)
                # Для CURSOR_TASK результат придёт через webhook, поэтому просто продолжаем
                # В реальной реализации здесь можно было бы ждать завершения через webhook,
                # но для совместимости с текущей архитектурой оставляем асинхронное выполнение

            elif step.type == DevFlowStepType.RUN_TESTS:
                success = await run_tests_for_step(step, chat_id)
                if not success:
                    error_message = (
                        f"❌ Шаг {step_index}/{total_steps} завершился с ошибкой: "
                        f"тесты не прошли.\n\n"
                        f"DevFlow '{scenario.name}' остановлен."
                    )
                    await send_telegram_message(chat_id, error_message)
                    logger_instance.error(
                        "DevFlow: scenario '%s' stopped at step %d due to test failure",
                        scenario.name,
                        step_index,
                    )
                    return  # Останавливаем сценарий

            elif step.type == DevFlowStepType.SERVER_UPDATE:
                success = await run_server_update_for_step(step, chat_id)
                if not success:
                    error_message = (
                        f"⚠️ Шаг {step_index}/{total_steps} завершился с предупреждением: "
                        f"не удалось обновить сервер.\n\n"
                        f"Продолжаем выполнение сценария."
                    )
                    await send_telegram_message(chat_id, error_message)
                    logger_instance.warning(
                        "DevFlow: scenario '%s' step %d server update failed, continuing",
                        scenario.name,
                        step_index,
                    )
                    # Для SERVER_UPDATE не останавливаем сценарий, только предупреждаем

            else:
                error_message = (
                    f"❌ Неизвестный тип шага: {step.type}\n\n"
                    f"DevFlow '{scenario.name}' остановлен."
                )
                await send_telegram_message(chat_id, error_message)
                logger_instance.error(
                    "DevFlow: scenario '%s' stopped at step %d due to unknown step type: %s",
                    scenario.name,
                    step_index,
                    step.type,
                )
                return

            # Сообщение о завершении шага (для не-CURSOR_TASK шагов)
            if step.type != DevFlowStepType.CURSOR_TASK:
                completion_message = (
                    f"✅ Шаг {step_index}/{total_steps} завершён: {step_name}"
                )
                await send_telegram_message(chat_id, completion_message)

        except Exception as e:
            error_message = (
                f"❌ Шаг {step_index}/{total_steps} завершился с ошибкой: {str(e)}\n\n"
                f"DevFlow '{scenario.name}' остановлен."
            )
            await send_telegram_message(chat_id, error_message)
            logger_instance.exception(
                "DevFlow: scenario '%s' stopped at step %d due to exception",
                scenario.name,
                step_index,
            )
            return

    # Финальное сообщение
    final_message = (
        f"🎉 DevFlow '{scenario.name}' успешно завершён ✅\n\n"
        f"Всего шагов: {total_steps}."
    )
    await send_telegram_message(chat_id, final_message)

    logger_instance.info(
        "DevFlow: scenario '%s' completed successfully for chat_id=%s",
        scenario.name,
        chat_id,
    )


# ============================================================================
# Предопределённые сценарии DevFlow
# ============================================================================


def create_simple_ma_scenario(flow_id: str) -> DevFlowScenario:
    """
    Создаёт DevFlow-сценарий для разработки стратегии Simple Moving Average.

    Этот сценарий включает три шага CURSOR_TASK:
    1. Реализация стратегии simple_ma
    2. Добавление тестов для simple_ma
    3. Интеграция simple_ma в trader agent

    Args:
        flow_id: ID DevFlow сессии (для привязки к шагам)

    Returns:
        DevFlowScenario для simple_ma
    """
    from orchestrator.dev_flow import DEVFLOW_SIMPLE_MA_STEPS

    steps = []
    for idx, step_data in enumerate(DEVFLOW_SIMPLE_MA_STEPS, start=1):
        step = DevFlowStep(
            type=DevFlowStepType.CURSOR_TASK,
            name=step_data.get("id", f"step_{idx}"),
            description=step_data.get("description", step_data.get("title", "")),
            config={
                "flow_id": flow_id,
                "step_number": idx,
                "step_prompt": step_data.get("cursor_task_prompt", ""),
                "scenario_name": "simple_ma",
            },
        )
        steps.append(step)

    return DevFlowScenario(
        name="devflow_simple_ma",
        description="DevFlow сценарий: разработка и интеграция стратегии Simple Moving Average.",
        steps=steps,
    )


# Экспортируем функцию для создания сценария
simple_ma_scenario_factory = create_simple_ma_scenario

