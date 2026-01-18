import { motion } from 'framer-motion'
import { Play, Pause, TrendingUp, Brain, Target } from 'lucide-react'

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

            {/* ML & Sentiment Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Auto-Learning Info Card */}
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 }}
                    className="bg-gradient-to-br from-purple-500/10 to-cyan-500/10 backdrop-blur-xl border border-purple-500/30 rounded-2xl p-6"
                >
                    <div className="flex items-center gap-2 mb-6">
                        <Brain className="w-5 h-5 text-purple-400" />
                        <h2 className="text-xl font-semibold">Auto-Learning Active</h2>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center gap-3 text-emerald-400">
                            <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
                            <span>Bot optimizes strategy automatically</span>
                        </div>
                        <p className="text-slate-400 text-sm">
                            The bot uses reinforcement learning (DQN) to continuously improve trading decisions.
                            No manual tuning required!
                        </p>
                        <div className="grid grid-cols-2 gap-3 mt-4">
                            <div className="bg-slate-800/50 rounded-lg p-3">
                                <span className="text-slate-400 text-xs">Learning Rate</span>
                                <p className="text-white font-semibold">Adaptive</p>
                            </div>
                            <div className="bg-slate-800/50 rounded-lg p-3">
                                <span className="text-slate-400 text-xs">Status</span>
                                <p className="text-emerald-400 font-semibold">Active</p>
                            </div>
                        </div>
                        <button
                            onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'learning' } }))}
                            className="block w-full mt-4 text-center bg-purple-500/20 text-purple-400 border border-purple-500/30 py-2 rounded-lg hover:bg-purple-500/30 transition-colors cursor-pointer"
                        >
                            View Learning Progress →
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
