import re
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from keyboards.kb_for_employees import employees_list_ikb, employee_store_selection_ikb, employee_action_ikb, \
    employee_edit_ikb, back_only_ikb
from keyboards.kb_for_stores import delete_confirmation_ikb, main_menu_ikb
from states.states import Form
from i18n import _
from db.database import AsyncDatabase

router = Router()

logger = logging.getLogger(__name__)

@router.callback_query(F.data == "my_employees")
async def show_my_employees(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    if not employees:
        await callback.message.edit_text(
            await _(account_id, "no_employees"),
            reply_markup=await employees_list_ikb(account_id, [])
        )
    else:
        await callback.message.edit_text(
            await _(account_id, "choose_employee"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
    await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data == "add_employee")
async def add_employee_start(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    await callback.message.edit_text(
        await _(account_id, "enter_employee_name"),
        reply_markup=await back_only_ikb(account_id, "back_to_employees")
    )
    await state.update_data(main_message_id=callback.message.message_id)
    await state.set_state(Form.waiting_for_employee_name)
    await callback.answer()

@router.message(Form.waiting_for_employee_name)
async def employee_name_received(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    main_message_id = data.get("main_message_id")

    full_name = message.text.strip()
    await state.update_data(employee_name=full_name)

    try:
        await message.delete()
    except:
        pass

    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=main_message_id,
        text=await _(account_id, "enter_employee_phone_input"),
        reply_markup=await back_only_ikb(account_id, "back_to_employees")
    )
    await state.set_state(Form.waiting_for_employee_phone_input)

@router.message(Form.waiting_for_employee_phone_input)
async def employee_phone_input_received(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    phone = message.text.strip()
    await state.update_data(employee_phone=phone)
    await message.answer(
        await _(account_id, "enter_employee_code"),
        reply_markup=await back_only_ikb(account_id, "back_to_employees")
    )
    await state.set_state(Form.waiting_for_employee_code_input)

@router.message(Form.waiting_for_employee_code_input)
async def employee_code_input_received(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    main_message_id = data.get("main_message_id")

    access_code = message.text.strip()
    if not re.match(r'^\d{4}$', access_code):
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=main_message_id,
            text=await _(account_id, "invalid_access_code"),
            reply_markup=await back_only_ikb(account_id, "back_to_employees")
        )
        return

    data = await state.get_data()
    full_name = data.get("employee_name")
    phone = data.get("employee_phone")

    try:
        async with AsyncDatabase() as db:
            employee_id = await db.create_employee(account_id, full_name, phone, access_code)
            await state.update_data(employee_id=employee_id, selected_stores=[])
            stores = await db.get_user_stores(account_id)

        if not stores:
            async with AsyncDatabase() as db:
                employees = await db.get_employees_by_owner(account_id)
            await message.answer(
                await _(account_id, "no_stores_for_employee"),
                reply_markup=await employees_list_ikb(account_id, employees)
            )
            await state.set_state(Form.waiting_for_employee_action)
            return

        await message.answer(
            await _(account_id, "select_employee_stores"),
            reply_markup=await employee_store_selection_ikb(account_id, stores)
        )
        await state.set_state(Form.waiting_for_employee_store_selection)
    except Exception as e:
        logging.error(f"Error creating employee: {str(e)}")
        async with AsyncDatabase() as db:
            employees = await db.get_employees_by_owner(account_id)
        await message.answer(
            await _(account_id, "error_creating_employee"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)

@router.callback_query(Form.waiting_for_employee_store_selection, F.data.startswith("toggle_store_"))
async def toggle_employee_store(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    store_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected_stores = data.get("selected_stores", [])

    if store_id in selected_stores:
        selected_stores.remove(store_id)
    else:
        selected_stores.append(store_id)

    await state.update_data(selected_stores=selected_stores)

    async with AsyncDatabase() as db:
        stores = await db.get_user_stores(account_id)

    await callback.message.edit_text(
        await _(account_id, "select_employee_stores"),
        reply_markup=await employee_store_selection_ikb(account_id, stores, selected_stores)
    )
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_store_selection, F.data == "select_all_stores")
async def select_all_employee_stores(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        stores = await db.get_user_stores(account_id)

    selected_stores = [store[0] for store in stores]
    await state.update_data(selected_stores=selected_stores)
    await callback.message.edit_text(
        await _(account_id, "select_employee_stores"),
        reply_markup=await employee_store_selection_ikb(account_id, stores, selected_stores)
    )
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_store_selection, F.data == "confirm_store_selection")
async def confirm_employee_store_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()

    employee_id = data.get("employee_id") or data.get("selected_employee_id")
    selected_stores = data.get("selected_stores", [])
    is_editing_stores = data.get("is_editing_stores", False)

    if not employee_id:
        async with AsyncDatabase() as db:
            employees = await db.get_employees_by_owner(account_id)
        await callback.message.answer(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        await callback.answer()
        return

    selected_stores = [store_id for store_id in selected_stores if store_id is not None and isinstance(store_id, int)]
    if not selected_stores:
        async with AsyncDatabase() as db:
            stores = await db.get_user_stores(account_id)
        await callback.message.answer(
            await _(account_id, "no_stores_selected"),
            reply_markup=await employee_store_selection_ikb(account_id, stores, selected_stores)
        )
        await callback.answer()
        return

    full_name = data.get("employee_name")
    if not full_name:
        async with AsyncDatabase() as db:
            employees = await db.get_employees_by_owner(account_id)
        employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)
        if employee:
            full_name = employee['full_name']

    try:
        logging.info(f"Назначение магазинов {selected_stores} сотруднику {employee_id} для пользователя {account_id}")

        async with AsyncDatabase() as db:
            await db.assign_employee_to_stores(employee_id, selected_stores)
            stores = await db.get_user_stores(account_id)
            employees = await db.get_employees_by_owner(account_id)

        selected_store_names = [store[1] for store in stores if store[0] in selected_stores]
        stores_text = ", ".join(selected_store_names) if selected_store_names else await _(account_id,
                                                                                           "no_stores_assigned")

        translation_key = "employee_stores_updated" if is_editing_stores else "employee_added"

        await callback.message.answer(
            await _(account_id, translation_key, full_name=full_name, stores=stores_text),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
    except Exception as e:
        logging.error(f"Ошибка при назначении магазинов сотруднику {employee_id}: {str(e)}")
        async with AsyncDatabase() as db:
            employees = await db.get_employees_by_owner(account_id)
        await callback.message.answer(
            await _(account_id, "error_adding_employee"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data.startswith("select_employee_"))
async def select_employee(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    employee_id = int(callback.data.split("_")[2])

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)

    if not employee:
        await callback.message.edit_text(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        return

    store_names = ", ".join(filter(None, employee['store_names'])) or await _(account_id, "no_stores_assigned")
    status = await _(account_id, "enabled" if employee['is_active'] else "disabled")
    message_text = await _(account_id, "employee_info",
                           full_name=employee['full_name'],
                           phone=employee['phone'],
                           access_code=employee['access_code'],
                           stores=store_names,
                           status=status)

    await callback.message.edit_text(
        message_text,
        reply_markup=await employee_action_ikb(account_id)
    )
    await state.update_data(selected_employee_id=employee_id)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data == "edit_employee")
async def edit_employee_start(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    await callback.message.edit_text(
        await _(account_id, "choose_edit_employee_field"),
        reply_markup=await employee_edit_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_employee_edit_field)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data == "delete_employee")
async def delete_employee_start(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)

    if not employee:
        await callback.message.edit_text(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        return

    await callback.message.edit_text(
        await _(account_id, "confirm_delete_employee", full_name=employee['full_name']),
        reply_markup=await delete_confirmation_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_confirm_employee_delete)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data == "toggle_employee_status")
async def toggle_employee_status(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)

    if not employee:
        await callback.message.answer(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        return

    async with AsyncDatabase() as db:
        await db.update_employee_field(employee_id, "is_active", not employee['is_active'])
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)
    store_names = ", ".join(filter(None, employee['store_names'])) or await _(account_id, "no_stores_assigned")
    status = await _(account_id, "enabled" if employee['is_active'] else "disabled")
    message_text = await _(account_id, "employee_info",
                           full_name=employee['full_name'],
                           phone=employee['phone'],
                           access_code=employee['access_code'],
                           stores=store_names,
                           status=status)

    await callback.message.edit_text(
        message_text,
        reply_markup=await employee_action_ikb(account_id)
    )
    await callback.answer()

@router.callback_query(Form.waiting_for_confirm_employee_delete, F.data.in_(["confirm_delete", "cancel_delete"]))
async def handle_confirm_employee_delete(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)
    if not employee:
        await callback.message.edit_text(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        await callback.answer()
        return

    if callback.data == "confirm_delete":
        async with AsyncDatabase() as db:
            success = await db.delete_employee(employee_id)
            employees = await db.get_employees_by_owner(account_id)

        if success:
            await callback.message.edit_text(
                await _(account_id, "employee_deleted", full_name=employee['full_name']),
                reply_markup=await employees_list_ikb(account_id, employees)
            )
            await state.set_state(Form.waiting_for_employee_action)
        else:
            await callback.message.edit_text(
                await _(account_id, "employee_deletion_error"),
                reply_markup=await employees_list_ikb(account_id, employees)
            )
    else:
        store_names = ", ".join(filter(None, employee['store_names'])) or await _(account_id, "no_stores_assigned")
        status = await _(account_id, "enabled" if employee['is_active'] else "disabled")
        message_text = await _(account_id, "employee_info",
                               full_name=employee['full_name'],
                               phone=employee['phone'],
                               access_code=employee['access_code'],
                               stores=store_names,
                               status=status)
        await callback.message.edit_text(
            message_text,
            reply_markup=await employee_action_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_edit_field, F.data.in_(
    ["edit_employee_name", "edit_employee_phone", "edit_employee_code", "edit_employee_stores"]))
async def edit_employee_field(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")

    field_map = {
        "edit_employee_name": "full_name",
        "edit_employee_phone": "phone",
        "edit_employee_code": "access_code",
        "edit_employee_stores": "stores"
    }
    field = field_map[callback.data]

    if field == "stores":
        await state.update_data(is_editing_stores=True)

        async with AsyncDatabase() as db:
            stores = await db.get_user_stores(account_id)
            employees = await db.get_employees_by_owner(account_id)

        if not stores:
            await callback.message.answer(
                await _(account_id, "no_stores_for_employee"),
                reply_markup=await employee_action_ikb(account_id)
            )
            await state.set_state(Form.waiting_for_employee_action)
            return

        employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)
        await state.update_data(selected_stores=employee['store_ids'] or [])
        await callback.message.answer(
            await _(account_id, "select_employee_stores"),
            reply_markup=await employee_store_selection_ikb(account_id, stores, employee['store_ids'])
        )
        await state.set_state(Form.waiting_for_employee_store_selection)
    else:
        await callback.message.answer(
            await _(account_id, f"enter_new_{field}"),
            reply_markup=await back_only_ikb(account_id, "back_to_employee")
        )
        await state.update_data(field_to_edit=field)
        await state.set_state(Form.waiting_for_employee_edit_value)
    await callback.answer()

@router.message(Form.waiting_for_employee_edit_value)
async def employee_edit_value_received(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")
    field = data.get("field_to_edit")
    value = message.text.strip()

    if field == "access_code" and not re.match(r'^\d{4}$', value):
        await message.answer(
            await _(account_id, "invalid_access_code"),
            reply_markup=await back_only_ikb(account_id, "back_to_employee")
        )
        return

    try:
        async with AsyncDatabase() as db:
            await db.update_employee_field(employee_id, field, value)
            employees = await db.get_employees_by_owner(account_id)

        employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)
        store_names = ", ".join(filter(None, employee['store_names'])) or await _(account_id, "no_stores_assigned")
        status = await _(account_id, "enabled" if employee['is_active'] else "disabled")
        message_text = await _(account_id, "employee_info",
                               full_name=employee['full_name'],
                               phone=employee['phone'],
                               access_code=employee['access_code'],
                               stores=store_names,
                               status=status)
        await message.answer(
            message_text,
            reply_markup=await employee_action_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_employee_action)
    except Exception as e:
        logging.error(f"Error updating employee field: {str(e)}")
        await message.answer(
            await _(account_id, "error_updating_employee"),
            reply_markup=await employee_action_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_employee_action)

@router.callback_query(Form.waiting_for_employee_name, F.data == "back_to_employees")
async def back_from_employee_name(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    await callback.message.edit_text(
        await _(account_id, "choose_employee"),
        reply_markup=await employees_list_ikb(account_id, employees)
    )
    await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data == "back_to_employees")
async def back_to_employees(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        user = await db.get_user(account_id)

    if not user or user.get("role") != "owner":
        await callback.message.answer(
            await _(account_id, "access_denied"),
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        await callback.answer()
        return

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    if not employees:
        await callback.message.answer(
            await _(account_id, "no_employees"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        await callback.answer()
        return

    try:
        await callback.message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete message: {e}")

    await callback.message.answer(
        await _(account_id, "choose_employee"),
        reply_markup=await employees_list_ikb(account_id, employees)
    )
    await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_edit_field, F.data == "back_to_employee")
async def handle_back_to_employee(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)

    if not employee:
        await callback.message.answer(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        await callback.answer()
        return

    store_names = ", ".join(filter(None, employee['store_names'])) or await _(account_id, "no_stores_assigned")
    status = await _(account_id, "enabled" if employee['is_active'] else "disabled")
    message_text = await _(account_id, "employee_info",
                           full_name=employee['full_name'],
                           phone=employee['phone'],
                           access_code=employee['access_code'],
                           stores=store_names,
                           status=status)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        message_text,
        reply_markup=await employee_action_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_edit_value, F.data == "back_to_employee")
async def back_to_employee_edit_from_value(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    employee_id = data.get("selected_employee_id")

    async with AsyncDatabase() as db:
        employees = await db.get_employees_by_owner(account_id)

    employee = next((emp for emp in employees if emp['employee_id'] == employee_id), None)

    if not employee:
        await callback.message.answer(
            await _(account_id, "employee_not_found"),
            reply_markup=await employees_list_ikb(account_id, employees)
        )
        await state.set_state(Form.waiting_for_employee_action)
        await callback.answer()
        return

    store_names = ", ".join(filter(None, employee['store_names'])) or await _(account_id, "no_stores_assigned")
    status = await _(account_id, "enabled" if employee['is_active'] else "disabled")
    message_text = await _(account_id, "employee_info",
                           full_name=employee['full_name'],
                           phone=employee['phone'],
                           access_code=employee['access_code'],
                           stores=store_names,
                           status=status)

    await callback.message.answer(
        message_text,
        reply_markup=await employee_action_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_employee_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_employee_action, F.data == "back_to_main_menu")
async def handle_back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    await state.clear()

    await callback.message.edit_text(
        await _(account_id, "main_menu"),
        reply_markup=await main_menu_ikb(account_id)
    )
    await callback.answer()