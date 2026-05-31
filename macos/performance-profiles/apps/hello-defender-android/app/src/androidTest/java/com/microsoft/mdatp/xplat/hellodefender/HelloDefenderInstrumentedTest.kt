package com.microsoft.mdatp.xplat.hellodefender

import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class HelloDefenderInstrumentedTest {
    @Test
    fun helloTitleIsVisible() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val view = activity.findViewById<android.view.View>(R.id.helloTitle)
                assertNotNull("helloTitle view must exist", view)
                assertEquals(
                    "helloTitle must be visible",
                    android.view.View.VISIBLE,
                    view.visibility,
                )
            }
        }
    }
}
