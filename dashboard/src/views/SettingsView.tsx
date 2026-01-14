import { motion } from 'framer-motion'
import { Key, Bell, Shield, Download, Globe } from 'lucide-react'

export default function SettingsView() {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex-1 p-8"
        >
            <div className="mb-6">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                    Settings
                </h1>
                <p className="text-slate-400 mt-2">Configure your trading bot and preferences</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* API Configuration */}
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Key className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-xl font-semibold">API Configuration</h2>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Binance API Key</label>
                            <input
                                type="password"
                                defaultValue="••••••••••••••••"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Binance API Secret</label>
                            <input
                                type="password"
                                defaultValue="••••••••••••••••"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>
                        <button className="w-full bg-cyan-500 hover:bg-cyan-600 text-white font-semibold py-3 rounded-lg transition-colors">
                            Update API Keys
                        </button>
                    </div>
                </motion.div>

                {/* Notifications */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Bell className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-xl font-semibold">Notifications</h2>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Telegram Bot Token</label>
                            <input
                                type="text"
                                placeholder="Enter bot token"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Telegram Chat ID</label>
                            <input
                                type="text"
                                placeholder="Enter chat ID"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>
                        <button className="w-full bg-cyan-500 hover:bg-cyan-600 text-white font-semibold py-3 rounded-lg transition-colors">
                            Save Telegram Settings
                        </button>
                    </div>
                </motion.div>

                {/* Trading Preferences */}
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Shield className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-xl font-semibold">Trading Preferences</h2>
                    </div>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-4 bg-slate-800/30 rounded-lg">
                            <div>
                                <div className="font-semibold text-white">Demo Mode</div>
                                <div className="text-sm text-slate-400">Use simulated trading</div>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" defaultChecked />
                                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500"></div>
                            </label>
                        </div>
                        <div className="flex items-center justify-between p-4 bg-slate-800/30 rounded-lg">
                            <div>
                                <div className="font-semibold text-white">Dry Run</div>
                                <div className="text-sm text-slate-400">Test without real trades</div>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" defaultChecked />
                                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500"></div>
                            </label>
                        </div>
                        <div className="flex items-center justify-between p-4 bg-slate-800/30 rounded-lg">
                            <div>
                                <div className="font-semibold text-white">Auto Trading</div>
                                <div className="text-sm text-slate-400">Enable automated trades</div>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" className="sr-only peer" />
                                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-lg peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-500"></div>
                            </label>
                        </div>
                    </div>
                </motion.div>

                {/* Display Settings */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.4 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Globe className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-xl font-semibold">Display Settings</h2>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Language</label>
                            <select className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white">
                                <option>English</option>
                                <option selected>Deutsch</option>
                                <option>Español</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Timezone</label>
                            <select className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white">
                                <option>UTC</option>
                                <option selected>Europe/Berlin</option>
                                <option>America/New_York</option>
                            </select>
                        </div>
                    </div>
                </motion.div>

                {/* Export Data */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 }}
                    className="lg:col-span-2 bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Download className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-xl font-semibold">Export Data</h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <button className="bg-slate-800/50 hover:bg-slate-800 border border-slate-700 text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2">
                            <Download className="w-4 h-4" />
                            Export Trades (CSV)
                        </button>
                        <button className="bg-slate-800/50 hover:bg-slate-800 border border-slate-700 text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2">
                            <Download className="w-4 h-4" />
                            Export Performance
                        </button>
                        <button className="bg-slate-800/50 hover:bg-slate-800 border border-slate-700 text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2">
                            <Download className="w-4 h-4" />
                            Export All Data
                        </button>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    )
}
