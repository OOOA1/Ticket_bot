from .handlers_wave import register_wave_handlers
from .handlers_tickets import register_tickets_handlers
from .handlers_admins import register_admins_handlers
from .handlers_broadcast import register_broadcast_handlers
from .handlers_report import register_report_handler
from .handlers_invites import register_invites_handlers
from .handlers_mass_send import register_mass_send_handler
from .handlers_help import register_help_handlers

def register_admin_handlers(bot):
    # Регистрирует все админские хендлеры для бота.
    
    register_wave_handlers(bot)
    register_tickets_handlers(bot)
    register_admins_handlers(bot)
    register_mass_send_handler(bot)
    register_broadcast_handlers(bot)
    register_invites_handlers(bot)
    register_help_handlers(bot)
    register_report_handler(bot)
