import { motion } from 'framer-motion'
import { Play, Pause, Settings, TrendingUp, Brain, Target } from 'lucide-react'

export default function BotsView() {
    const botRunning = true

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex-1 p-8"
        >
            <div className="mb-6">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                    Bot Configuration
                </h1>
                <p className="text-slate-400 mt-2">Manage your trading bot and strategies</p>
            </div>

            {/* Bot Status */}
            <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6 mb-8"
            >
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold mb-2">ETH Trading Bot</h2>
                        <div className="flex items-center gap-2">
                            <div className={`w-3 h-3 rounded-full ${botRunning ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
                            <span className={`text-sm font-medium ${botRunning ? 'text-green-400' : 'text-red-400'}`}>
                                {botRunning ? 'Running' : 'Stopped'}
                            </span>
                        </div>
                    </div>
                    <button className={`px-6 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all duration-300 ${botRunning
                            ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
                            : 'bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30'
                        }`}>
                        {botRunning ? <><Pause className="w-5 h-5" /> Stop Bot</> : <><Play className="w-5 h-5" /> Start Bot</>}
                    </button>
                </div>
            </motion.div>

            {/* Strategy Settings */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 }}
                    className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Settings className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-xl font-semibold">Strategy Settings</h2>
                    </div>

                    <div className="space-y-6">
                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Risk Level</label>
                            <select className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white">
                                <option>Conservative</option>
                                <option selected>Moderate</option>
                                <option>Aggressive</option>
                            </select>
                        </div>

                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Daily Target (%)</label>
                            <input
                                type="number"
                                defaultValue="1.0"
                                step="0.1"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>

                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Max Drawdown (%)</label>
                            <input
                                type="number"
                                defaultValue="5.0"
                                step="0.5"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>

                        <div>
                            <label className="text-sm text-slate-400 mb-2 block">Position Size (USDT)</label>
                            <input
                                type="number"
                                defaultValue="100"
                                step="10"
                                className="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-3 text-white"
                            />
                        </div>

                        <button className="w-full bg-cyan-500 hover:bg-cyan-600 text-white font-semibold py-3 rounded-lg transition-colors">
                            Save Settings
                        </button>
                    </div>
                </motion.div>

                {/* ML & Sentiment */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 }}
                    className="space-y-6"
                >
                    {/* ML Model Info */}
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Brain className="w-5 h-5 text-cyan-400" />
                            <h2 className="text-xl font-semibold">ML Model</h2>
                        </div>
                        <div className="space-y-3">
                            <div className="flex justify-between">
                                <span className="text-slate-400">Model Type</span>
                                <span className="text-white font-semibold">SGDClassifier</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">Accuracy</span>
                                <span className="text-green-400 font-semibold">68.5%</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">Training Samples</span>
                                <span className="text-white font-semibold">1,247</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">Last Updated</span>
                                <span className="text-white font-semibold">2 hours ago</span>
                            </div>
                        </div>
                    </div>

                    {/* Sentiment Analysis */}
                    <div className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/50 rounded-2xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <TrendingUp className="w-5 h-5 text-cyan-400" />
                            <h2 className="text-xl font-semibold">Sentiment Analysis</h2>
                        </div>
                        <div className="space-y-3">
                            <div className="flex justify-between">
                                <span className="text-slate-400">Current Sentiment</span>
                                <span className="text-green-400 font-semibold">Bullish (0.72)</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">Sources</span>
                                <span className="text-white font-semibold">RSS Feeds</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-400">Last Analysis</span>
                                <span className="text-white font-semibold">5 min ago</span>
                            </div>
                        </div>
                    </div>

                    {/* Performance Target */}
                    <div className="bg-gradient-to-r from-cyan-500/20 to-blue-500/20 backdrop-blur-xl border border-cyan-500/30 rounded-2xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Target className="w-5 h-5 text-cyan-400" />
                            <h2 className="text-xl font-semibold">Daily Target</h2>
                        </div>
                        <div className="text-4xl font-bold text-cyan-400 mb-2">1.0%</div>
                        <div className="text-sm text-slate-300">Optimized for consistent gains</div>
                    </div>
                </motion.div>
            </div>
        </motion.div>
    )
}
